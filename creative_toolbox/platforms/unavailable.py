"""Fail-closed adapter: unrelated local tools remain usable after native setup fails."""
from ..core import Snapshot


class UnavailableBackend:
    available = False
    label = "创作保护暂不可用"

    def __init__(self, platform, reason):
        self.platform, self.unavailable_reason = platform, reason

    def capture(self):
        return Snapshot(None, 0, 0, blocked=self.unavailable_reason,
                        can_send=False, permission=self.unavailable_reason)

    def send(self, expected, shortcut, idle_required):
        return False, self.unavailable_reason
