"""Bounded image jobs. Worker owns its SQLite connection; Qt widgets stay on the GUI thread."""
from pathlib import Path
from threading import Event
import uuid

from PySide6.QtCore import QThread, Signal
from .library import AssetStore, Cancelled, MAX_BATCH, MAX_PIXELS, check_cancel


class AssetJob(QThread):
    progress = Signal(int, int, str)

    def __init__(self, root, kind, payload, parent=None):
        super().__init__(parent)
        self.root, self.kind, self.payload = Path(root), kind, payload
        self.cancel = Event()
        self.result = {"kind": kind, "state": "failed", "ids": [], "duplicates": 0, "errors": []}

    def run(self):
        store, task_id, temporary = None, None, None
        done = 0
        try:
            store = AssetStore(self.root)
            total = len(self.payload) if self.kind == "import" else 1
            if self.kind == "import" and total > MAX_BATCH:
                raise ValueError("每次最多导入 100 张图片")
            task_id = store.start_task(self.kind, total)
            if self.kind in ("import", "clipboard"):
                if self.kind == "clipboard":
                    image = self.payload
                    if image.isNull() or image.width() * image.height() > MAX_PIXELS:
                        raise ValueError("剪贴板图片无效或超过 4000 万像素")
                    temporary = store.root / "staging" / (uuid.uuid4().hex + ".png")
                    check_cancel(self.cancel)
                    if not image.save(str(temporary), "PNG"):
                        raise OSError("剪贴板图片写入失败")
                    paths = [temporary]
                else:
                    paths = self.payload
                for index, path in enumerate(paths):
                    check_cancel(self.cancel)
                    try:
                        asset_id, duplicate = store.add_file(
                            Path(path), self.cancel,
                            title="剪贴板图片" if self.kind == "clipboard" else None,
                            origin="剪贴板" if self.kind == "clipboard" else None)
                        self.result["ids"].append(asset_id)
                        self.result["duplicates"] += int(duplicate)
                    except Cancelled:
                        raise
                    except Exception as exc:
                        self.result["errors"].append(f"{Path(path).name}: {exc}")
                    done = index + 1
                    store.finish_task(task_id, "running", done, self.result["errors"])
                    self.progress.emit(done, len(paths), "正在收集图片")
                self.result["state"] = "partial" if self.result["errors"] else "success"
                if self.result["errors"] and not self.result["ids"]:
                    self.result["state"] = "failed"
            elif self.kind == "backup":
                store.export_backup(self.payload, self.cancel,
                                    lambda d, t: self.progress.emit(d, t, "正在校验并备份"))
                self.result.update(state="success", path=str(self.payload))
                done = 1
            elif self.kind == "restore":
                archive, destination = self.payload
                AssetStore.restore_backup(archive, destination, self.cancel,
                                          lambda d, t: self.progress.emit(d, t, "正在恢复到独立目录"))
                self.result.update(state="success", path=str(destination))
                done = 1
            else:
                raise ValueError("未知素材任务")
        except Cancelled:
            self.result["state"] = "cancelled"
        except Exception as exc:
            self.result["errors"].append(str(exc))
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    self.result["errors"].append("临时文件未清理：" + str(exc))
            if store:
                try:
                    if task_id:
                        store.finish_task(task_id, self.result["state"], done, self.result["errors"])
                except Exception as exc:
                    self.result["errors"].append("任务状态未写入：" + str(exc))
                finally:
                    store.close()
