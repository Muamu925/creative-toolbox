from __future__ import annotations

import time
import os
from dataclasses import dataclass
from typing import Callable

from .core import Decision, Engine, Snapshot, resolve_shortcut, recheck
from .storage import Settings


@dataclass(frozen=True)
class Event:
    kind: str
    app: str
    message: str


class Controller:
    def __init__(self, backend, settings: Settings,
                 emit: Callable[[Event], None] = lambda event: None) -> None:
        self.backend, self.settings, self.emit = backend, settings, emit
        self.engine = Engine()
        self.automatic = False  # Never restore armed mode from disk.
        self.paused = False
        self.requests = 0
        self.observations = 0
        self._settle = None

    def restart(self) -> None:
        self.engine.reset()
        self._settle = None

    def tick(self, now: float | None = None) -> tuple[Snapshot, Decision]:
        now = time.monotonic() if now is None else now
        snapshot = self.backend.capture()
        if self._settle:
            pid, target, attempted = self._settle
            if now - attempted <= 1.5 and snapshot.target and (
                snapshot.target.identity, snapshot.target.pid, snapshot.target.window
            ) == (target.identity, target.pid, target.window):
                # OS injection can be delivered after SendInput returns. Consume its
                # final timestamp and any save-induced window title change conservatively.
                self.engine.mark_attempt(pid, target, attempted, snapshot.input_token)
                self.engine.mark_attempt(pid, snapshot.target, attempted, snapshot.input_token)
            else:
                self._settle = None
        profiles = [] if snapshot.target and snapshot.target.pid == os.getpid() else self.settings.profiles
        decision = self.engine.evaluate(snapshot, profiles, self.backend.platform,
                                        now, self.paused)
        if not decision.due:
            return snapshot, decision
        profile = next(p for p in self.settings.profiles if p.id == decision.profile_id)
        if not self.automatic:
            self.observations += 1
            self.engine.mark_attempt(profile.id, snapshot.target, now, snapshot.input_token)
            self.emit(Event("observe", profile.name, "满足通用规则；观察模式未发送快捷键"))
            return snapshot, Decision("observed", "观察完成：此时满足通用保存条件", profile.id)
        if profile.reminder_only:
            self.engine.mark_attempt(profile.id, snapshot.target, now, snapshot.input_token)
            self.emit(Event("reminder", profile.name, "已到保存时间；此应用仅提醒，请在合适时手动保存"))
            return snapshot, Decision("reminded", "已提醒，请在合适时手动保存", profile.id)
        style = self.settings.style if profile.style == "inherit" else profile.style
        custom = self.settings.custom if profile.style == "inherit" else profile.custom
        try:
            shortcut = resolve_shortcut(style, custom, self.backend.platform)
            # A second observation before calling the native adapter; native dispatch rechecks again.
            fresh = self.backend.capture()
            changed = recheck(snapshot, fresh, profile.idle)
            if changed:
                return fresh, Decision("cancelled", changed, profile.id)
            ok, message = self.backend.send(fresh, shortcut, profile.idle)
        except Exception as exc:
            ok, message = False, f"无法发送快捷键：{type(exc).__name__}；已暂停此应用"
        # Consume our injected input so it cannot trigger endless saves while idle.
        try:
            after = self.backend.capture()
            token = after.input_token
        except Exception:
            token = snapshot.input_token
        self.engine.mark_attempt(profile.id, snapshot.target, now, token, failed=not ok)
        if ok:
            self.requests += 1
            self._settle = (profile.id, snapshot.target, now)
        self.emit(Event("request" if ok else "error", profile.name, message))
        return snapshot, Decision("requested" if ok else "failed", message, profile.id)
