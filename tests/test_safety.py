import ctypes
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from creative_toolbox.controller import Controller
from creative_toolbox.core import Engine, Profile, Shortcut, Snapshot, Target, recheck, resolve_shortcut
from creative_toolbox.storage import Settings, Store


TARGET = Target(r"C:\Apps\Editor.exe", "Editor", 90001, "window-1", "draft.design")


def snapshot(**kwargs):
    return replace(Snapshot(TARGET, 4, 10), **kwargs)


def profile(**kwargs):
    return replace(Profile("editor", "Editor", TARGET.identity, "win32", interval=10, idle=2), **kwargs)


class FakeBackend:
    platform = "win32"
    label = "测试后端"

    def __init__(self):
        self.snap = snapshot()
        self.sent = []
        self.fail = False
        self.switch_on_capture = False
        self.capture_count = 0

    def capture(self):
        self.capture_count += 1
        if self.switch_on_capture and self.capture_count == 2:
            return snapshot(target=replace(TARGET, window="other-window"))
        return self.snap

    def send(self, expected, shortcut, idle_required):
        self.sent.append(shortcut)
        self.snap = replace(self.snap, input_token=self.snap.input_token + 1)
        return (False, "模拟权限失败") if self.fail else (True, "已发送保存请求 · 结果未确认")


class SafetyTests(unittest.TestCase):
    def run_until(self, controller, end, start=0):
        result = None
        for half in range(int(start * 2), int(end * 2) + 1):
            result = controller.tick(half / 2)
        return result

    def controller(self, **kwargs):
        self.backend = FakeBackend()
        self.events = []
        return Controller(self.backend, Settings([profile(**kwargs)]), self.events.append)

    def test_observer_never_sends_and_does_not_repeat_without_activity(self):
        c = self.controller()
        self.run_until(c, 30)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(c.observations, 1)
        self.assertEqual(self.events[0].kind, "observe")

    def test_automatic_requires_opt_in_each_instance(self):
        c = self.controller()
        self.assertFalse(c.automatic)
        c.automatic = True
        self.run_until(c, 30)
        self.assertEqual(len(self.backend.sent), 1)
        self.assertEqual(c.requests, 1)
        self.assertIn("未确认", self.events[0].message)
        self.assertFalse(Controller(self.backend, c.settings).automatic)

    def test_own_injected_input_cannot_rearm_save_loop(self):
        c = self.controller()
        c.automatic = True
        self.run_until(c, 60)
        self.assertEqual(len(self.backend.sent), 1)
        self.backend.snap = snapshot(input_token=99)
        self.run_until(c, 65, 60.5)
        self.assertEqual(len(self.backend.sent), 2)

    def test_held_modifier_blocks_even_with_long_idle(self):
        c = self.controller()
        c.automatic = True
        self.backend.snap = snapshot(pressed=True, idle=999)
        self.run_until(c, 20)
        self.assertEqual(self.backend.sent, [])

    def test_unlisted_or_similarly_named_executable_never_matches(self):
        c = self.controller()
        c.automatic = True
        self.backend.snap = snapshot(target=replace(TARGET, identity=r"C:\Apps\FakeEditor.exe"))
        self.run_until(c, 20)
        self.assertEqual(self.backend.sent, [])

    def test_full_path_does_not_match_same_name_in_another_folder(self):
        self.assertFalse(profile().matches(replace(TARGET, identity=r"C:\Other\Editor.exe"), "win32"))
        self.assertTrue(profile(identity="editor.exe").matches(TARGET, "win32"))

    def test_modal_and_input_activity_block_sending(self):
        for change in ({"blocked": "另存弹窗"}, {"idle": 0.3}, {"idle": float("nan")}):
            c = self.controller()
            c.automatic = True
            self.backend.snap = snapshot(**change)
            self.run_until(c, 20)
            self.assertEqual(self.backend.sent, [])

    def test_race_between_decision_and_send_cancels(self):
        c = self.controller()
        c.automatic = True
        self.run_until(c, 9.5)
        self.backend.capture_count = 0
        self.backend.switch_on_capture = True
        _, decision = c.tick(10)
        self.assertEqual(decision.code, "cancelled")
        self.assertEqual(self.backend.sent, [])

    def test_document_title_change_invalidates_request(self):
        self.assertTrue(recheck(snapshot(), snapshot(target=replace(TARGET, title="other.design")), 2))

    def test_new_input_and_permission_denial_invalidate_request(self):
        self.assertTrue(recheck(snapshot(), snapshot(input_token=11), 2))
        self.assertTrue(recheck(snapshot(), snapshot(can_send=False), 2))

    def test_recording_profile_only_reminds(self):
        c = self.controller(reminder_only=True)
        c.automatic = True
        self.run_until(c, 20)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.events[0].kind, "reminder")

    def test_failures_suspend_instead_of_repeatedly_injecting(self):
        c = self.controller()
        c.automatic = True
        self.backend.fail = True
        self.run_until(c, 30)
        self.backend.snap = snapshot(input_token=100)
        self.run_until(c, 50, 30.5)
        self.assertEqual(len(self.backend.sent), 1)
        self.assertEqual(c.requests, 0)
        self.assertIn("editor", c.engine.failed)

    def test_resume_from_sleep_restarts_interval(self):
        c = self.controller()
        c.automatic = True
        self.run_until(c, 9)
        _, decision = c.tick(100)
        self.assertFalse(decision.due)
        self.assertEqual(self.backend.sent, [])

    def test_pause_cancels_pending_action(self):
        c = self.controller()
        c.automatic = True
        self.run_until(c, 9)
        c.paused = True
        self.run_until(c, 20, 9.5)
        self.assertEqual(self.backend.sent, [])

    def test_late_synthetic_input_and_save_title_change_do_not_repeat(self):
        c = self.controller()
        c.automatic = True
        self.run_until(c, 10)
        self.backend.snap = snapshot(input_token=77, target=replace(TARGET, title="draft.design — saved"))
        self.run_until(c, 40, 10.5)
        self.assertEqual(len(self.backend.sent), 1)

    def test_lock_clears_pending_window_timers(self):
        c = self.controller()
        c.automatic = True
        self.run_until(c, 9)
        self.backend.snap = snapshot(target=None, blocked="锁屏")
        self.run_until(c, 20, 9.5)
        self.backend.snap = snapshot()
        self.run_until(c, 22, 20.5)
        self.assertEqual(self.backend.sent, [])

    def test_toolbox_process_is_never_an_automation_target(self):
        import os
        c = self.controller()
        c.automatic = True
        self.backend.snap = snapshot(target=replace(TARGET, pid=os.getpid()))
        self.run_until(c, 20)
        self.assertEqual(self.backend.sent, [])

    def test_shortcut_styles_and_application_override(self):
        self.assertEqual(resolve_shortcut("auto", "", "win32").text(), "Ctrl+S")
        self.assertEqual(resolve_shortcut("auto", "", "darwin").text(), "Cmd+S")
        self.assertEqual(resolve_shortcut("windows", "", "darwin").text(), "Ctrl+S")
        with self.assertRaises(ValueError):
            resolve_shortcut("macos", "", "win32")
        c = self.controller(style="custom", custom="Ctrl+Shift+S")
        c.settings.style = "custom"
        c.settings.custom = "Alt+S"
        c.automatic = True
        self.run_until(c, 10)
        self.assertEqual(self.backend.sent[0].text(), "Ctrl+Shift+S")

    def test_invalid_shortcuts_are_rejected(self):
        for invalid in ("S", "Shift+S", "Ctrl+Ctrl+S", "Win+S", "Ctrl+Enter", "Ctrl++S"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Shortcut.parse(invalid)

    def test_settings_roundtrip_and_corruption_does_not_overwrite_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp), "win32")
            store.save(Settings([profile()], "custom", "Ctrl+Shift+S"))
            loaded = store.load()
            self.assertEqual(loaded.profiles[0], profile())
            self.assertEqual(loaded.custom, "Ctrl+Shift+S")
            store.path.write_text("not json", encoding="utf-8")
            defaults = store.load()
            self.assertTrue(store.warning)
            self.assertTrue(all(not p.enabled for p in defaults.profiles))
            self.assertEqual(store.path.read_text(), "not json")

    def test_logs_do_not_include_window_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp), "win32")
            store.event("request", "Editor", "已发送保存请求 · 结果未确认")
            raw = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(TARGET.title, raw)
            self.assertEqual(json.loads(raw)["kind"], "request")


@unittest.skipUnless(sys.platform == "win32", "Win32 adapter")
class WindowsTests(unittest.TestCase):
    def test_native_capture_reads_without_injecting(self):
        from creative_toolbox.platforms.windows import WindowsBackend, INPUT
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertGreaterEqual(WindowsBackend().capture().idle, 0)

    def test_native_packet_batch_has_balanced_modifiers(self):
        from creative_toolbox.platforms.windows import WindowsBackend
        backend = WindowsBackend()
        backend.capture = lambda: snapshot()
        received = []

        class Sink:
            def SendInput(self, count, packets, size):
                received.extend((packets[i].ki.wVk, packets[i].ki.dwFlags) for i in range(count))
                return count

        backend.user = Sink()
        ok, _ = backend.send(snapshot(), Shortcut.parse("Ctrl+Shift+S"), 2)
        self.assertTrue(ok)
        self.assertEqual(received, [(17, 0), (16, 0), (83, 0), (83, 2), (16, 2), (17, 2)])


if __name__ == "__main__":
    unittest.main()
