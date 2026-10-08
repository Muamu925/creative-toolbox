"""macOS desktop conventions around the existing local-first workspace."""
from PySide6.QtCore import QByteArray, QEvent, QObject, QSettings, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .workspace import TOOLS
from .mac_workspace import CommandPalette


class MacDesktop(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.actions = {}
        self.state = QSettings(str(window.store.root / "window-state.ini"), QSettings.Format.IniFormat)
        geometry = self.state.value("geometry")
        if isinstance(geometry, QByteArray):
            window.restoreGeometry(geometry)
        self.launcher = CommandPalette(window)
        self.launcher.open_requested.connect(window.open_tool)
        self.launcher.route_requested.connect(self.open_route)
        self.make_menus()
        QApplication.instance().installEventFilter(self)

    def action(self, menu, key, title, callback, shortcut=None, role=QAction.MenuRole.NoRole):
        action = QAction(title, self)
        action.setMenuRole(role)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        menu.addAction(action)
        self.actions[key] = action
        return action

    def make_menus(self):
        w = self.window
        bar = w.menuBar()
        bar.setNativeMenuBar(True)
        app_menu = bar.addMenu("创作工具箱")
        self.action(app_menu, "about", "关于创作工具箱", self.about, role=QAction.MenuRole.AboutRole)
        self.action(app_menu, "settings", "设置…", lambda: self.open_route("settings"),
                    "Ctrl+,", QAction.MenuRole.PreferencesRole)
        self.action(app_menu, "quit", "退出创作工具箱", w.quit_app,
                    QKeySequence.StandardKey.Quit, QAction.MenuRole.QuitRole)
        file_menu = bar.addMenu("文件")
        self.action(file_menu, "collect", "收集图片…", lambda: w.open_tool("assets"), "Ctrl+Shift+I")
        self.action(file_menu, "resources", "搜索资料…", lambda: self.open_route("library"), "Ctrl+Shift+F")
        self.action(file_menu, "data", "在 Finder 中打开资料文件夹", w.open_data)
        file_menu.addSeparator()
        self.action(file_menu, "close", "关闭窗口", self.close_window, QKeySequence.StandardKey.Close)

        edit_menu = bar.addMenu("编辑")
        for key, title, shortcut in (
            ("undo", "撤销", QKeySequence.StandardKey.Undo),
            ("redo", "重做", QKeySequence.StandardKey.Redo),
            ("cut", "剪切", QKeySequence.StandardKey.Cut),
            ("copy", "复制", QKeySequence.StandardKey.Copy),
            ("paste", "粘贴", QKeySequence.StandardKey.Paste),
            ("selectAll", "全选", QKeySequence.StandardKey.SelectAll),
        ):
            self.action(edit_menu, key, title, lambda method=key: self.edit(method), shortcut)
        edit_menu.aboutToShow.connect(self.update_edit_actions)
        QApplication.instance().focusChanged.connect(self.update_edit_actions)

        view = bar.addMenu("显示")
        self.action(view, "launcher", "快速打开…", self.show_launcher, "Ctrl+K")
        self.action(view, "find", "搜索当前页面", self.focus_search, QKeySequence.StandardKey.Find)
        view.addSeparator()
        for number, (key, title) in enumerate((("home", "工作台"), ("library", "资源库"), ("tools", "全部工具"), ("projects", "项目")), 1):
            self.action(view, key, title, lambda route=key: self.open_route(route), f"Ctrl+{number}")
        sidebar = self.action(view, "sidebar", "显示侧栏", self.toggle_sidebar, "Ctrl+Alt+S")
        sidebar.setCheckable(True)
        sidebar.setChecked(True)

        tools_menu = bar.addMenu("工具")
        for tool in TOOLS:
            self.action(tools_menu, "tool_" + tool.id, tool.name, lambda key=tool.id: w.open_tool(key))
        tools_menu.addSeparator()
        self.action(tools_menu, "floating", "悬浮色卡", w.open_floating_palette)
        windows = bar.addMenu("窗口")
        self.action(windows, "minimize", "最小化", w.showMinimized, "Ctrl+M")
        self.action(windows, "show", "打开创作工具箱", w.show_main, "Ctrl+0")
        self.action(windows, "fullscreen", "进入 / 退出全屏", self.toggle_fullscreen, "Ctrl+Meta+F")
        help_menu = bar.addMenu("帮助")
        self.action(help_menu, "help", "创作工具箱帮助", w.open_help, "Ctrl+Shift+/")

    def about(self):
        QMessageBox.about(self.window, "关于创作工具箱",
                          f"创作工具箱 · Creative Toolbox\n版本 {__version__}\n\n"
                          "图片、字体、配色与日常换算。\n资料保存在本机，无需账号。")

    def edit(self, method):
        widget = QApplication.focusWidget()
        callback = getattr(widget, method, None)
        if callable(callback):
            callback()

    def update_edit_actions(self, *_):
        widget = QApplication.focusWidget()
        for method in ("undo", "redo", "cut", "copy", "paste", "selectAll"):
            self.actions[method].setEnabled(callable(getattr(widget, method, None)))

    def open_route(self, route):
        self.window.show_main()
        self.window.navigate(route)
        if route == "library" and not self.window.backup_busy:
            self.window.resource_search.search.setFocus()

    def show_launcher(self):
        if self.window.backup_busy:
            return
        self.window.show_main()
        self.launcher.search.clear()
        self.launcher.open()

    def focus_search(self):
        if self.window.backup_busy:
            return
        from PySide6.QtWidgets import QLineEdit
        page = self.window.pages.currentWidget()
        inputs = [widget for widget in page.findChildren(QLineEdit)
                  if widget.isVisible() and widget.isEnabled()
                  and ("搜索" in widget.accessibleName() or "搜索" in widget.placeholderText())]
        if inputs:
            inputs[0].setFocus()
            inputs[0].selectAll()
        else:
            self.show_launcher()

    def toggle_sidebar(self):
        self.window.sidebar_material.setVisible(self.actions["sidebar"].isChecked())

    def toggle_fullscreen(self):
        if self.window.isFullScreen():
            self.window.showNormal()
        else:
            self.window.showFullScreen()

    def close_window(self):
        window = QApplication.activeWindow() or self.window
        window.close()

    def eventFilter(self, watched, event):
        # Qt's Cocoa delegate emits this on Dock reopen as well as activation.
        if (watched is QApplication.instance() and event.type() == QEvent.Type.ApplicationActivate
                and not self.window.isVisible() and not self.window.quitting):
            QTimer.singleShot(0, self.reopen)
        return False

    def reopen(self):
        if not self.window.quitting and not self.window.isVisible():
            self.window.show_main()

    def save_geometry(self):
        self.state.setValue("geometry", self.window.saveGeometry())
        self.state.sync()
        if self.state.status() != QSettings.Status.NoError:
            self.window.footer.setText("本次窗口位置未能保存。")

    def shutdown(self):
        self.save_geometry()
        QApplication.instance().removeEventFilter(self)
        try:
            QApplication.instance().focusChanged.disconnect(self.update_edit_actions)
        except (RuntimeError, TypeError):
            pass
        self.launcher.close()
