"""Project specifications and independent resource copies; no host-file writes."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from uuid import uuid4

from .design_core import normalize_hex

MAX_DATABASE = 8 * 1024 * 1024
MAX_PROJECTS = 200
MAX_RESOURCES = 100
SCENES = {
    "design": ("平面 / UI", (("canvas", "画布尺寸"), ("ppi", "PPI"), ("bleed", "出血要求"), ("color", "色彩要求"))),
    "video": ("视频", (("canvas", "画面尺寸"), ("fps", "帧率"), ("duration", "时长要求"), ("audio", "音频规格"))),
    "music": ("音乐", (("bpm", "BPM 与拍值"), ("meter", "拍号"), ("key", "调性"), ("sample_rate", "采样率"), ("bit_depth", "位深"))),
    "three_d": ("三维", (("unit", "场景单位"), ("canvas", "渲染尺寸"), ("fps", "帧率"), ("texture", "贴图规格"))),
}
FIELDS = dict(pair for _, fields in SCENES.values() for pair in fields)
FIELDS["canvas"] = "画布 / 输出尺寸"


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def string(value, maximum, label, required=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value or (required and not value.strip()):
        raise ValueError(f"{label}无效或超过长度限制")
    return value.strip()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("项目或资源标识无效")
    return value


def new_project(name, scene="design"):
    return dict(id=uuid4().hex, name=name, scene=scene, client="", directory="", due="",
                notes="", delivery="", specs={}, resources=[], archived=False,
                revision=0, created=timestamp(), updated=timestamp())


def palette_copy(palette):
    return dict(id=uuid4().hex, kind="palette", name=palette["name"],
                colors=[dict(name=color.get("name", ""), hex=color["hex"]) for color in palette["colors"]])


def font_copy(family, style="Regular", note=""):
    return dict(id=uuid4().hex, kind="font", family=family, style=style, note=note)


def image_reference(library_id, asset):
    return dict(id=uuid4().hex, kind="image", library_id=library_id, asset_id=asset["id"],
                hash=asset["hash"], title=asset["title"])


def validate(project):
    if not isinstance(project, dict):
        raise ValueError("项目记录无效")
    p = deepcopy(project)
    expected = set(new_project(""))
    if set(p) != expected:
        raise ValueError("项目字段不完整或包含未知字段")
    identifier(p["id"])
    for field, maximum in (("name", 120), ("client", 200), ("directory", 2000),
                           ("due", 10), ("notes", 4000), ("delivery", 4000)):
        p[field] = string(p[field], maximum, field, field == "name")
    if p["scene"] not in SCENES or type(p["archived"]) is not bool:
        raise ValueError("项目类型或归档状态无效")
    if type(p["revision"]) is not int or p["revision"] < 0:
        raise ValueError("项目修订号无效")
    if p["due"]:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["due"]):
            raise ValueError("截止日期请使用 YYYY-MM-DD 格式")
        date.fromisoformat(p["due"])
    for key in ("created", "updated"):
        value = string(p[key], 64, "记录时间", True)
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("记录时间缺少时区")
    if not isinstance(p["specs"], dict) or not set(p["specs"]) <= set(FIELDS):
        raise ValueError("项目规格字段无效")
    p["specs"] = {k: string(v, 500, FIELDS[k]) for k, v in p["specs"].items()}
    if not isinstance(p["resources"], list) or len(p["resources"]) > MAX_RESOURCES:
        raise ValueError("每个项目最多保存 100 项资源")
    ids = set()
    for item in p["resources"]:
        if not isinstance(item, dict):
            raise ValueError("项目资源格式无效")
        rid = identifier(item.get("id"))
        if rid in ids:
            raise ValueError("项目资源标识重复")
        ids.add(rid)
        kind = item.get("kind")
        if kind == "image":
            if set(item) != {"id", "kind", "library_id", "asset_id", "hash", "title"}:
                raise ValueError("图片引用字段无效")
            identifier(item["library_id"])
            identifier(item["asset_id"])
            if not isinstance(item["hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["hash"]):
                raise ValueError("图片内容摘要无效")
            string(item["title"], 200, "图片名称", True)
        elif kind == "palette":
            if set(item) != {"id", "kind", "name", "colors"}:
                raise ValueError("项目配色字段无效")
            string(item["name"], 120, "配色名称", True)
            if not isinstance(item["colors"], list) or len(item["colors"]) > 100:
                raise ValueError("每个配色副本最多包含 100 个颜色")
            for color in item["colors"]:
                if not isinstance(color, dict) or set(color) != {"name", "hex"}:
                    raise ValueError("项目颜色字段无效")
                string(color["name"], 80, "颜色名称")
                color["hex"] = normalize_hex(color["hex"])
        elif kind == "font":
            if set(item) != {"id", "kind", "family", "style", "note"}:
                raise ValueError("字体候选字段无效")
            string(item["family"], 500, "字体家族", True)
            string(item["style"], 120, "字体样式", True)
            string(item["note"], 4000, "字体备注")
        else:
            raise ValueError("未知项目资源类型")
    if len(json.dumps(p, ensure_ascii=False).encode()) > 128 * 1024:
        raise ValueError("单个项目记录不能超过 128 KiB")
    return p


class ProjectStore:
    """Short-lived SQLite connections; optimistic revisions prevent lost updates."""
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "projects.sqlite3"
        self.warning = ""
        self.read_only = False
        try:
            self.list()
        except (ValueError, OSError, sqlite3.Error, TypeError, KeyError) as exc:
            self.warning = f"项目资料未载入，原文件已保留。请备份并修复后重试。原因：{exc}"
            self.read_only = True

    def _connect(self, readonly=True):
        if self.path.is_symlink():
            raise ValueError("项目数据库不能使用符号链接")
        if self.path.exists() and self.path.stat().st_size > MAX_DATABASE:
            raise ValueError("项目数据库超过 8 MiB 限制")
        db = sqlite3.connect(self.path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True)
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("不支持的项目数据库版本")
        except Exception:
            db.close()
            raise
        return db

    def list(self):
        if not self.path.exists():
            return []
        db = self._connect()
        try:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("项目数据库完整性检查失败")
            rows = db.execute("SELECT id, payload FROM projects ORDER BY rowid DESC").fetchmany(MAX_PROJECTS + 1)
            if len(rows) > MAX_PROJECTS:
                raise ValueError("项目数量超过上限")
            results = []
            for key, payload in rows:
                p = validate(json.loads(payload))
                if p["id"] != key:
                    raise ValueError("项目标识与数据库记录不一致")
                results.append(p)
            return sorted(results, key=lambda p: p["updated"], reverse=True)
        finally:
            db.close()

    def get(self, key):
        for project in self.list():
            if project["id"] == key:
                return project
        raise ValueError("项目已不存在")

    def save(self, project):
        if self.read_only:
            raise ValueError(self.warning)
        candidate = validate(project)
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            # Publish a valid empty database atomically; never adopt an unknown file.
            fd, stage = tempfile.mkstemp(dir=self.root, suffix=".sqlite3")
            os.close(fd)
            try:
                db = sqlite3.connect(stage)
                try:
                    db.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                    db.execute("PRAGMA user_version=1")
                    db.commit()
                finally:
                    db.close()
                os.link(stage, self.path)
            finally:
                Path(stage).unlink(missing_ok=True)
        db = self._connect(False)
        try:
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={MAX_DATABASE // page_size}")
            with db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT payload FROM projects WHERE id=?", (candidate["id"],)).fetchone()
                if existing:
                    previous = validate(json.loads(existing[0]))
                    if previous["revision"] != candidate["revision"]:
                        raise ValueError("项目已在其他位置更新，请重新打开后编辑")
                elif candidate["revision"] != 0:
                    raise ValueError("原项目记录缺失，不能覆盖保存")
                elif db.execute("SELECT count(*) FROM projects").fetchone()[0] >= MAX_PROJECTS:
                    raise ValueError("最多支持 200 个项目，包括已归档项目")
                candidate["revision"] += 1
                candidate["updated"] = timestamp()
                payload = json.dumps(candidate, ensure_ascii=False)
                total = db.execute("SELECT coalesce(sum(length(cast(payload AS BLOB))),0) FROM projects WHERE id != ?", (candidate["id"],)).fetchone()[0]
                if total + len(payload.encode()) > 6 * 1024 * 1024:
                    raise ValueError("项目资料容量已达上限")
                db.execute("INSERT INTO projects VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                           (candidate["id"], payload))
        finally:
            db.close()
        return deepcopy(candidate)

    def duplicate(self, key, name):
        project = self.get(key)
        project.update(id=uuid4().hex, name=name, revision=0, archived=False, created=timestamp())
        for item in project["resources"]:
            item["id"] = uuid4().hex
        return self.save(project)

    def snapshot(self, destination):
        self.list()  # Validate all records before including the database in a backup.
        source = self._connect()
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()


def resolve_image(root, item):
    """Only resolve exact identities in the active library; never search by title."""
    from .assets.library import AssetStore
    from .resources_search import asset_root
    store = AssetStore.open_readonly(asset_root(root))
    try:
        if item["library_id"] != store.library_id:
            raise ValueError("图片属于其他素材库")
        asset = store.get(item["asset_id"])
        if asset["hash"] != item["hash"]:
            raise ValueError("图片内容与项目引用不一致")
        if asset["deleted"]:
            raise ValueError("图片已移入回收站")
        path = store.path_for(item["asset_id"])
        if not path.is_file():
            raise ValueError("图片原件缺失")
        return asset, path
    finally:
        store.close()


def image_projects(root, library_id, asset_id):
    """List saved references, including archived projects, before trashing an image."""
    store = ProjectStore(root)
    if store.read_only:
        raise ValueError("项目引用暂时无法检查，请先修复项目资料")
    return [p["name"] for p in store.list() if any(
        r["kind"] == "image" and r["library_id"] == library_id and r["asset_id"] == asset_id
        for r in p["resources"])]


def project_markdown(project, root):
    p = validate(project)
    # Values are plain user-authored text, escaped instead of becoming HTML/links.
    def escape(value):
        return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", str(value)).replace("\r", "").replace("\n", "  \n")
    rows = [f"# {escape(p['name'])}", "", "项目规格与资源说明", "",
            f"- 项目编号：{p['id']}", f"- 修订号：{p['revision']}",
            f"- 项目类型：{SCENES[p['scene']][0]}",
            f"- 更新日期：{p['updated']}", ""]
    for key, title in (("client", "客户 / 委托方"), ("due", "截止日期"), ("directory", "项目目录")):
        if p[key]:
            rows.append(f"- {title}：{escape(p[key])}")
    rows += ["", "## 项目规格", "", "以下为用户填写的项目要求，未经宿主工程自动检测。", ""]
    labels = {**FIELDS, **dict(SCENES[p["scene"]][1])}
    for key, title in labels.items():
        if p["specs"].get(key):
            rows.append(f"- {title}：{escape(p['specs'][key])}")
    for key, title in (("delivery", "交付要求"), ("notes", "项目备注")):
        if p[key]:
            rows += ["", f"## {title}", "", escape(p[key])]
    rows += ["", "## 项目资源", "", "配色与字体候选为独立项目副本；此说明不包含图片原件或字体文件。", ""]
    if not p["resources"]:
        rows.append("未关联资源。")
    for item in p["resources"]:
        if item["kind"] == "image":
            try:
                asset, _ = resolve_image(root, item)
                state, name = "可用", asset["title"]
            except (ValueError, OSError, sqlite3.Error) as exc:
                state, name = f"不可用：{exc}", item["title"]
            rows += [f"### 参考图片：{escape(name)}", "", f"状态：{escape(state)}",
                     f"素材库：{item['library_id']}；素材：{item['asset_id']}", ""]
        elif item["kind"] == "palette":
            rows += [f"### 项目配色：{escape(item['name'])}", ""]
            rows.extend(f"- {escape(c['name'] or '未命名颜色')}：`{c['hex']}`" for c in item["colors"])
            rows.append("")
        else:
            rows += [f"### 字体候选：{escape(item['family'])}", "", f"样式：{escape(item['style'])}",
                     "字体名称用于本机匹配，不构成字体文件或授权证明。", escape(item["note"]), ""]
    return "\n".join(rows) + "\n"


def export_project(project, root, output):
    output = Path(output)
    if output.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("请将项目说明导出到资料目录以外")
    data = project_markdown(project, root)
    fd, stage = tempfile.mkstemp(dir=output.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, output)
    finally:
        Path(stage).unlink(missing_ok=True)
    return output
