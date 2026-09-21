"""Local image inbox. Each connection belongs to its creating thread."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImageReader, QColorSpace

MAX_FILE = 50 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_ITEMS = 10_000
MAX_BATCH = 100
MAX_LIBRARY_BYTES = 5 * 1024**3


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled("操作已取消")


def inspect_image(path):
    reader = QImageReader(str(path))
    try:
        reader.setDecideFormatFromContent(True)
        reader.setAutoTransform(True)
        size = reader.size()
        fmt = bytes(reader.format()).decode("ascii", errors="ignore").lower()
        if fmt not in ("png", "jpeg", "jpg"):
            raise ValueError("仅支持 PNG / JPEG 图片")
        if not size.isValid() or size.width() * size.height() > MAX_PIXELS:
            raise ValueError("图片不能超过 4000 万像素")
        reader.setScaledSize(size.scaled(QSize(1200, 1200), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            raise ValueError("图片损坏或无法读取")
        if image.colorSpace().isValid():
            image.convertToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        return image, size.width(), size.height(), "jpg" if fmt in ("jpeg", "jpg") else "png"
    finally:
        if reader.device() is not None:
            reader.device().close()


class AssetStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "library.sqlite3"
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            tables = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if version not in (0, 1) or (version == 0 and tables):
                raise ValueError("不支持的素材库版本；原文件已保留")
            self.db.execute("PRAGMA foreign_keys=ON")
            if version == 0:
                self.db.executescript("""
                    BEGIN;
                    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE blobs (
                        hash TEXT PRIMARY KEY, ext TEXT NOT NULL, size INTEGER NOT NULL,
                        width INTEGER NOT NULL, height INTEGER NOT NULL);
                    CREATE TABLE assets (
                        id TEXT PRIMARY KEY, hash TEXT NOT NULL REFERENCES blobs(hash),
                        title TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
                        source TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL DEFAULT '',
                        notes TEXT NOT NULL DEFAULT '', reviewed INTEGER NOT NULL DEFAULT 0,
                        deleted INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
                    CREATE INDEX assets_hash ON assets(hash);
                    CREATE INDEX assets_created ON assets(created);
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                        total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
                        errors TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL);
                    PRAGMA user_version=1;
                    COMMIT;
                """)
                with self.db:
                    self.db.execute("INSERT INTO meta VALUES ('library_id', ?)", (uuid.uuid4().hex,))
            self.library_id = self.db.execute("SELECT value FROM meta WHERE key='library_id'").fetchone()[0]
            if not re.fullmatch(r"[0-9a-f]{32}", self.library_id):
                raise ValueError("素材库标识无效")
            (self.root / "originals").mkdir(exist_ok=True)
            (self.root / "previews").mkdir(exist_ok=True)
            (self.root / "staging").mkdir(exist_ok=True)
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def recover_tasks(self):
        with self.db:
            count = self.db.execute("UPDATE tasks SET state='interrupted' WHERE state='running'").rowcount
        return count

    def blob_path(self, digest, ext, preview=False):
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or ext not in ("png", "jpg"):
            raise ValueError("素材文件标识无效")
        return self.root / ("previews" if preview else "originals") / (digest + ("." + ext))

    def get(self, asset_id):
        row = self.db.execute("""SELECT a.*, b.ext, b.size, b.width, b.height
            FROM assets a JOIN blobs b ON a.hash=b.hash WHERE a.id=?""", (asset_id,)).fetchone()
        if not row:
            raise ValueError("素材已不存在")
        result = dict(row)
        result["tags"] = json.loads(result["tags"])
        return result

    def path_for(self, asset_id, preview=False):
        asset = self.get(asset_id)
        return self.blob_path(asset["hash"], "png" if preview else asset["ext"], preview)

    def list_assets(self, query="", scope="all", offset=0, limit=100):
        if scope not in ("all", "inbox", "trash"):
            raise ValueError("未知筛选")
        where, params = ["a.deleted=?"], [int(scope == "trash")]
        if scope == "inbox":
            where.append("a.reviewed=0")
        # instr matches literal text; '%' and '_' are not wildcard expressions.
        # Python casefold provides consistent CJK/Unicode matching across platforms.
        rows = self.db.execute("""SELECT a.*, b.ext, b.width, b.height, b.size
            FROM assets a JOIN blobs b ON a.hash=b.hash WHERE """ + " AND ".join(where)
            + " ORDER BY a.created DESC, a.rowid DESC", params)
        words = query.casefold().split()
        matches = []
        total = 0
        for row in rows:
            item = dict(row)
            item["tags"] = json.loads(item["tags"])
            haystack = " ".join([item["title"], *item["tags"], item["source"], item["notes"]]).casefold()
            if all(word in haystack for word in words):
                if offset <= total < offset + limit:
                    matches.append(item)
                total += 1
        return matches, total

    def counts(self):
        row = self.db.execute("""SELECT COUNT(*),
            COALESCE(SUM(deleted=0),0), COALESCE(SUM(deleted=0 AND reviewed=0),0),
            COALESCE(SUM(deleted=1),0) FROM assets""").fetchone()
        used = self.db.execute("SELECT COALESCE(SUM(size),0) FROM blobs").fetchone()[0]
        return {"total": row[0], "active": row[1], "inbox": row[2], "trash": row[3], "bytes": used}

    def add_file(self, source: Path, cancel=None, title=None, origin=None):
        source = Path(source)
        if not source.is_file() or source.is_symlink():
            raise ValueError("请选择普通图片文件，暂不导入文件夹或链接")
        if not 0 < source.stat().st_size <= MAX_FILE:
            raise ValueError("单张图片须为 1 字节至 50 MiB")
        if self.counts()["total"] >= MAX_ITEMS:
            raise ValueError("素材库已达到 10000 条记录上限")
        fd, temp = tempfile.mkstemp(dir=self.root / "staging", suffix=".import")
        stage = Path(temp)
        try:
            digest, size = hashlib.sha256(), 0
            with os.fdopen(fd, "wb") as target, source.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    check_cancel(cancel)
                    size += len(chunk)
                    if size > MAX_FILE:
                        raise ValueError("图片超过 50 MiB")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            check_cancel(cancel)
            preview, width, height, ext = inspect_image(stage)
            checksum = digest.hexdigest()
            duplicate = self.db.execute("SELECT 1 FROM blobs WHERE hash=?", (checksum,)).fetchone() is not None
            if not duplicate and self.counts()["bytes"] + size > MAX_LIBRARY_BYTES:
                raise ValueError("素材库原件达到 5 GiB 上限")
            destination = self.blob_path(checksum, ext)
            # A failed earlier index commit may have left this immutable file behind.
            if destination.exists():
                if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest() != checksum:
                    raise ValueError("已有托管文件校验失败；请恢复备份")
            else:
                os.replace(stage, destination)
            check_cancel(cancel)
            preview_path = self.blob_path(checksum, "png", True)
            if not preview_path.exists():
                preview_stage = self.root / "staging" / (uuid.uuid4().hex + ".png")
                try:
                    if not preview.save(str(preview_stage), "PNG"):
                        raise OSError("预览图写入失败")
                    os.replace(preview_stage, preview_path)
                finally:
                    preview_stage.unlink(missing_ok=True)
            check_cancel(cancel)
            asset_id = uuid.uuid4().hex
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO blobs VALUES (?,?,?,?,?)",
                                (checksum, ext, size, width, height))
                self.db.execute("""INSERT INTO assets
                    (id,hash,title,origin,created) VALUES (?,?,?,?,?)""",
                    (asset_id, checksum, (title or source.stem)[:200],
                     (origin if origin is not None else str(source.resolve()))[:4000], now()))
            return asset_id, duplicate
        finally:
            stage.unlink(missing_ok=True)

    def update(self, asset_id, title, tags, source, notes, reviewed):
        title, source, notes = title.strip(), source.strip(), notes.strip()
        tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
        if not title or len(title) > 200 or len(source) > 2000 or len(notes) > 4000:
            raise ValueError("名称须为 1–200 字；来源至多 2000 字，备注至多 4000 字")
        if len(tags) > 20 or any(len(tag) > 40 for tag in tags):
            raise ValueError("最多 20 个标签，每个不超过 40 字")
        with self.db:
            changed = self.db.execute("""UPDATE assets SET title=?,tags=?,source=?,notes=?,reviewed=?
                WHERE id=?""", (title, json.dumps(tags, ensure_ascii=False), source, notes,
                               int(bool(reviewed)), asset_id)).rowcount
            if not changed:
                raise ValueError("素材已不存在")

    def set_deleted(self, asset_id, deleted):
        with self.db:
            if not self.db.execute("UPDATE assets SET deleted=? WHERE id=?",
                                   (int(bool(deleted)), asset_id)).rowcount:
                raise ValueError("素材已不存在")

    def start_task(self, kind, total):
        task_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO tasks (id,kind,state,total,created) VALUES (?,?,'running',?,?)",
                            (task_id, kind, total, now()))
        return task_id

    def finish_task(self, task_id, state, done, errors):
        with self.db:
            self.db.execute("UPDATE tasks SET state=?,done=?,errors=? WHERE id=?",
                            (state, done, json.dumps(errors, ensure_ascii=False), task_id))

    def export_backup(self, output: Path, cancel=None, progress=lambda done, total: None):
        """Caller serializes edits/imports until this snapshot is complete."""
        output = Path(output)
        if output.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("请选择素材库目录以外的备份位置")
        fd, temp = tempfile.mkstemp(dir=output.parent, suffix=".tmp")
        os.close(fd)
        stage = Path(temp)
        try:
            with tempfile.TemporaryDirectory(dir=self.root / "staging") as directory:
                snapshot = Path(directory) / "library.sqlite3"
                target = sqlite3.connect(snapshot)
                try:
                    self.db.backup(target)
                finally:
                    target.close()
                blobs = list(self.db.execute("SELECT hash,ext,size FROM blobs"))
                entries = [{"path": "library.sqlite3", "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                            "size": snapshot.stat().st_size}]
                with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_STORED) as archive:
                    archive.write(snapshot, "library.sqlite3")
                    for index, row in enumerate(blobs):
                        check_cancel(cancel)
                        path = self.blob_path(row["hash"], row["ext"])
                        if path.is_symlink() or path.stat().st_size != row["size"]:
                            raise ValueError("素材原件缺失或大小不符，备份未完成")
                        digest = hashlib.sha256()
                        arcpath = "originals/" + path.name
                        with path.open("rb") as stream, archive.open(arcpath, "w") as dest:
                            while chunk := stream.read(1024 * 1024):
                                check_cancel(cancel)
                                digest.update(chunk)
                                dest.write(chunk)
                        if digest.hexdigest() != row["hash"]:
                            raise ValueError("素材原件校验失败，备份未完成")
                        entries.append({"path": arcpath, "sha256": row["hash"], "size": row["size"]})
                        progress(index + 1, len(blobs))
                    check_cancel(cancel)
                    archive.writestr("manifest.json", json.dumps(
                        {"schema": 1, "library_id": self.library_id, "files": entries}, ensure_ascii=False))
            check_cancel(cancel)
            os.replace(stage, output)
        finally:
            stage.unlink(missing_ok=True)

    @classmethod
    def restore_backup(cls, archive_path: Path, destination: Path, cancel=None,
                       progress=lambda done, total: None):
        """Restore into a new directory only; never overwrite the active library."""
        destination = Path(destination)
        if destination.exists():
            raise ValueError("恢复目标必须为新目录")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix="restore-") as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)) or len(names) > MAX_ITEMS + 2:
                    raise ValueError("备份条目重复或超限")
                if archive.getinfo("manifest.json").file_size > 4 * 1024**2:
                    raise ValueError("备份清单过大")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), list):
                    raise ValueError("不支持的备份格式")
                files = manifest["files"]
                expected = [entry["path"] for entry in files]
                if set(names) != set(expected) | {"manifest.json"} or len(expected) != len(set(expected)):
                    raise ValueError("备份清单不匹配")
                total_bytes = 0
                for index, entry in enumerate(files):
                    check_cancel(cancel)
                    name, size = entry["path"], entry["size"]
                    if name != "library.sqlite3" and not re.fullmatch(r"originals/[0-9a-f]{64}\.(png|jpg)", name):
                        raise ValueError("备份包含不允许的路径")
                    if type(size) is not int or size < 0 or size > (64 * 1024**2 if name == "library.sqlite3" else MAX_FILE):
                        raise ValueError("备份文件超限")
                    total_bytes += size
                    if total_bytes > MAX_LIBRARY_BYTES + 64 * 1024**2 or archive.getinfo(name).file_size != size:
                        raise ValueError("备份大小无效")
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    digest, written = hashlib.sha256(), 0
                    with archive.open(name) as stream, path.open("wb") as output:
                        while chunk := stream.read(1024 * 1024):
                            check_cancel(cancel)
                            written += len(chunk)
                            if written > size:
                                raise ValueError("备份解压超限")
                            digest.update(chunk)
                            output.write(chunk)
                    if written != size or digest.hexdigest() != entry["sha256"]:
                        raise ValueError("备份内容校验失败")
                    progress(index + 1, len(files))
            probe = sqlite3.connect((root / "library.sqlite3").as_uri() + "?mode=ro", uri=True)
            try:
                if probe.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("不支持的素材库版本")
                if probe.execute("PRAGMA quick_check").fetchone()[0] != "ok" or probe.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("备份数据库无效")
                identity = probe.execute("SELECT value FROM meta WHERE key='library_id'").fetchone()[0]
                if identity != manifest["library_id"] or not re.fullmatch(r"[0-9a-f]{32}", identity):
                    raise ValueError("备份库标识不匹配")
                if probe.execute("SELECT count(*) FROM assets").fetchone()[0] > MAX_ITEMS:
                    raise ValueError("备份记录过多")
                blobnames = set()
                for digest, ext, size, width, height in probe.execute("SELECT * FROM blobs"):
                    if not re.fullmatch(r"[0-9a-f]{64}", digest) or ext not in ("png", "jpg"):
                        raise ValueError("备份素材标识无效")
                    name = f"originals/{digest}.{ext}"
                    path = root / name
                    if name not in expected or path.stat().st_size != size:
                        raise ValueError("备份缺少原件")
                    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        raise ValueError("原件摘要与索引不符")
                    blobnames.add(name)
                if set(expected) != blobnames | {"library.sqlite3"}:
                    raise ValueError("备份存在未索引的文件")
                for title, tags, source, origin, notes in probe.execute("SELECT title,tags,source,origin,notes FROM assets"):
                    decoded = json.loads(tags)
                    if (not all(isinstance(v, str) for v in (title, source, origin, notes))
                            or not isinstance(decoded, list) or len(decoded) > 20
                            or not all(isinstance(t, str) and len(t) <= 40 for t in decoded)
                            or not 0 < len(title) <= 200 or len(source) > 2000
                            or len(origin) > 4000 or len(notes) > 4000):
                        raise ValueError("备份整理信息无效")
            finally:
                probe.close()
            check_cancel(cancel)
            # Rebuild bounded previews after validation, before making restored library visible.
            recovered = cls(root)
            try:
                for row in recovered.db.execute("SELECT hash,ext FROM blobs"):
                    check_cancel(cancel)
                    image, *_ = inspect_image(recovered.blob_path(row["hash"], row["ext"]))
                    if not image.save(str(recovered.blob_path(row["hash"], "png", True)), "PNG"):
                        raise OSError("恢复预览失败")
                recovered.recover_tasks()
            finally:
                recovered.close()
            os.replace(root, destination)
        return destination
