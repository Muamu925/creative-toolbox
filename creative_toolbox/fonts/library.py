"""Validated, atomic metadata storage. Never writes or removes font files."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

MAX_BYTES = 8 * 1024 * 1024


def empty():
    return {"schema": 1, "groups": {}, "fonts": {}, "preferences": {}}


def entry():
    return {"favorite": False, "groups": [], "tags": [], "alias": "", "note": "", "source": ""}


def string(value, limit, label, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"{label}为空或超过长度限制")
    return value


def validate(raw):
    if not isinstance(raw, dict) or type(raw.get("schema")) is not int or raw["schema"] != 1:
        raise ValueError("不支持的字体库版本")
    groups, fonts, prefs = raw.get("groups"), raw.get("fonts"), raw.get("preferences", {})
    if not isinstance(groups, dict) or len(groups) > 200:
        raise ValueError("分组格式无效，最多 200 个")
    if not isinstance(fonts, dict) or len(fonts) > 10000:
        raise ValueError("字体整理记录无效，最多 10000 个")
    names = set()
    for gid, name in groups.items():
        string(gid, 100, "分组标识", True)
        string(name, 80, "分组名称", True)
        if name.casefold() in names:
            raise ValueError("分组名称重复")
        names.add(name.casefold())
    normalized = {}
    for family, value in fonts.items():
        string(family, 500, "字体名称", True)
        if not isinstance(value, dict):
            raise ValueError("字体记录无效")
        item = entry()
        item.update({k: v for k, v in value.items() if k in item})
        if type(item["favorite"]) is not bool:
            raise ValueError("收藏状态无效")
        for key, limit in (("groups", 200), ("tags", 50)):
            values = item[key]
            if not isinstance(values, list) or len(values) > limit:
                raise ValueError("分组或标签数量超限")
            for v in values:
                string(v, 100 if key == "groups" else 40, "分组或标签", True)
            if len(set(values)) != len(values):
                raise ValueError("分组或标签重复")
        if any(g not in groups for g in item["groups"]):
            raise ValueError("字体引用了不存在的分组")
        for key, limit in (("alias", 120), ("note", 4000), ("source", 2000)):
            string(item[key], limit, key)
        normalized[family] = item
    if not isinstance(prefs, dict):
        raise ValueError("预览设置无效")
    size = prefs.get("size", 28)
    if type(size) is not int or not 8 <= size <= 96:
        raise ValueError("预览字号超出范围")
    sample = string(prefs.get("sample", ""), 2000, "预览文案")
    return {"schema": 1, "groups": dict(groups), "fonts": normalized,
            "preferences": {"size": size, "sample": sample}}


def read_file(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("字体备份不能超过 8 MB")
    try:
        return validate(json.loads(data))
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("字体备份无法读取") from exc


def write_file(path, data):
    path = Path(path)
    blob = json.dumps(validate(data), ensure_ascii=False, indent=2).encode("utf-8")
    if len(blob) > MAX_BYTES:
        raise ValueError("字体整理数据不能超过 8 MB")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class FontLibrary:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.data = validate(empty())
        self.warning = ""
        self.read_only = False
        if self.path and self.path.exists():
            try:
                self.data = read_file(self.path)
            except (ValueError, OSError) as exc:
                self.warning = f"字体整理数据未载入，原文件已保留；当前只读。请备份并修复 {self.path.name} 后重启。原因：{exc}"
                self.read_only = True

    def change(self, callback):
        if self.read_only:
            raise ValueError(self.warning)
        proposed = deepcopy(self.data)
        callback(proposed)
        proposed = validate(proposed)
        if self.path:
            write_file(self.path, proposed)
        self.data = proposed

    def metadata(self, family):
        return deepcopy(self.data["fonts"].get(family, entry()))

    def add_group(self, name):
        gid = str(uuid4())
        self.change(lambda d: d["groups"].update({gid: name.strip()}))
        return gid

    def rename_group(self, gid, name):
        if gid not in self.data["groups"]:
            raise ValueError("请先选择一个自定义分组")
        self.change(lambda d: d["groups"].update({gid: name.strip()}))

    def delete_group(self, gid):
        def update(d):
            if gid not in d["groups"]:
                raise ValueError("请选择自定义分组")
            del d["groups"][gid]
            for value in d["fonts"].values():
                value["groups"] = [g for g in value["groups"] if g != gid]
        self.change(update)

    def edit(self, families, **fields):
        def update(d):
            for family in families:
                d["fonts"].setdefault(family, entry()).update(deepcopy(fields))
        self.change(update)

    def membership(self, families, gid, add=True):
        def update(d):
            if gid not in d["groups"]:
                raise ValueError("请先创建或选择分组")
            for family in families:
                values = d["fonts"].setdefault(family, entry())["groups"]
                if add and gid not in values:
                    values.append(gid)
                elif not add and gid in values:
                    values.remove(gid)
        self.change(update)

    def tag(self, families, tag, add=True):
        tag = tag.strip()
        string(tag, 40, "标签", True)
        def update(d):
            for family in families:
                values = d["fonts"].setdefault(family, entry())["tags"]
                if add and tag not in values:
                    values.append(tag)
                elif not add and tag in values:
                    values.remove(tag)
        self.change(update)

    def merge(self, incoming):
        incoming = validate(incoming)
        conflicts = []
        def update(d):
            mapping = {}
            for gid, name in incoming["groups"].items():
                target = gid
                if gid in d["groups"] and d["groups"][gid] != name:
                    target = str(uuid4())
                if target not in d["groups"]:
                    candidate, n = name, 2
                    while candidate.casefold() in {v.casefold() for v in d["groups"].values()}:
                        suffix = f"（导入 {n}）"
                        candidate = name[:80-len(suffix)] + suffix
                        n += 1
                    d["groups"][target] = candidate
                mapping[gid] = target
            for family, source in incoming["fonts"].items():
                target = d["fonts"].setdefault(family, entry())
                target["favorite"] |= source["favorite"]
                target["groups"] = list(dict.fromkeys(target["groups"] + [mapping[g] for g in source["groups"]]))
                target["tags"] = list(dict.fromkeys(target["tags"] + source["tags"]))
                for key in ("alias", "note", "source"):
                    if not target[key]:
                        target[key] = source[key]
                    elif source[key] and source[key] != target[key]:
                        conflicts.append(f"{family} / {key}")
            # Imported preferences never replace the user's current working text.
        self.change(update)
        return conflicts
