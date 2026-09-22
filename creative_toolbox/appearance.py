"""Independent appearance preferences; never overwrite unreadable/future files."""
import json
import os
import tempfile
from pathlib import Path


class AppearanceStore:
    def __init__(self, path: Path):
        self.path = path
        self.reduced = False
        self.warning = ''
        self.read_only = False
        try:
            if path.exists():
                if path.stat().st_size > 4096:
                    raise ValueError('文件过大')
                raw = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(raw, dict) or type(raw.get('schema')) is not int or raw['schema'] != 1:
                    raise ValueError('不支持的版本')
                if type(raw.get('reduced_transparency')) is not bool:
                    raise ValueError('透明效果设置无效')
                self.reduced = raw['reduced_transparency']
        except (OSError, ValueError, TypeError) as exc:
            self.read_only = True
            self.warning = f'外观偏好未载入：{exc}。原文件保留，本次可临时调整。'

    def save(self, reduced: bool):
        if type(reduced) is not bool:
            raise ValueError('外观设置必须是布尔值')
        if self.read_only:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'schema': 1, 'reduced_transparency': reduced}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            self.reduced = reduced
            return True
        finally:
            if os.path.exists(name):
                os.unlink(name)