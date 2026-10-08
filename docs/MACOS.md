# Mac 使用说明 · 0.10.1

2026-10-08，北京时间。本次在现有 Python / PySide6 项目上重制 Mac 外壳；图片、字体、配色、换算、创作保护和备份继续使用原有实现与资料格式。

## 打开应用

本地构建生成 `dist/CreativeToolbox.app`，可直接打开。发布镜像为 `CreativeToolbox-0.10.1-macOS-arm64-unsigned.dmg`，打开后拖到 Applications。系统最低要求 macOS 13；此包面向 Apple Silicon。Intel 需要在对应架构环境单独构建。包未经过 Developer ID 签名或公证，发布包见 [GitHub 0.10.1](https://github.com/Muamu925/creative-toolbox/releases/tag/v0.10.1)。

正式应用使用 `~/Library/Application Support/CreativeToolbox`，沿用已有资料；开发启动器使用隔离的 `.runtime/mac-user`。从 Windows 迁移时使用资源库中的完整备份 / 恢复；不复制旧 `.venv`。字体备份只包含整理信息，不包含字体文件。

双击项目根目录 `启动 Mac 开发版.command` 可运行开发版。第一次会建立 `.venv-mac` 并安装依赖，需要网络与 Python 3.12 或更新版本。此目录与原 Windows 环境相互独立。

```sh
./'启动 Mac 开发版.command'
# 仅使用本地工具，不启动创作保护系统查询
./'启动 Mac 开发版.command' --safe-mode
```

## Mac 操作

| 操作 | 快捷键 |
| --- | --- |
| 快速打开工具 / 页面 | ⌘K，输入关键词，↑↓ 选择，回车打开，Esc 关闭 |
| 搜索当前页；无搜索框时打开工具搜索 | ⌘F |
| 搜索图片、色板与字体整理资料 | ⌘⇧F |
| 工作台 / 资源库 / 全部工具 | ⌘1 / ⌘2 / ⌘3 |
| 项目 | ⌘4 |
| 设置 | ⌘, |
| 打开图片素材页 | ⌘⇧I |
| 显示 / 隐藏侧栏 | ⌘⌥S |
| 关闭当前窗口 | ⌘W |
| 重新显示主窗口 | ⌘0、Dock 图标或菜单栏图标 |
| 最小化 / 全屏 | ⌘M / ⌃⌘F |
| 退出整个工具箱 | ⌘Q |

关闭主窗口后应用继续运行，正在使用的页面与内容保留。退出时沿用原有备份和导入任务保护，字体偏好在退出时写入。窗口几何信息单独保存在资料目录的 `window-state.ini`；它不进入完整资料备份，迁移后使用新电脑布局。

界面目前采用浅色外观，使用系统字体和原生窗口控件。减少动态效果继续有效；Mac 外壳为不透明中性表面，所以减少透明效果不会改变其视觉。

## 创作保护与权限

图片、字体、配色、搜索和换算不需要辅助功能或输入监控权限。创作保护先检查权限；未授权时返回等待状态，不查询按键、空闲时长或发送事件。设置页提供系统权限入口。应用每次仍从观察模式开始，不会恢复自动保存开关。

截图参数自动使用无输入监控的安全后端。真实编辑软件的自动保存兼容性、非美式键盘、自定义组合键以及授权后的连续工作场景仍需逐一验证；本次未向其他应用发送保存按键。

## 开发与打包

```sh
.venv-mac/bin/python -m pip install -r requirements.txt -r requirements-build.txt
QT_QPA_PLATFORM=offscreen .venv-mac/bin/python -m unittest discover -v
.venv-mac/bin/python tools/mac_smoke.py
.venv-mac/bin/python tools/build.py
```

`tools/CreativeToolbox-macOS.spec` 维护 Bundle ID、版本、Retina 支持、最低系统版本、应用分类和图标；`build.py` 生成应用和附 Applications 快捷入口的 DMG。在受限沙箱中，原生窗口服务与 hdiutil 可能不可用，应在正常 Mac 桌面环境构建和验收。

## 本次验证

- 164 项自动化测试：162 项通过，2 项 Windows 专用测试在 Mac 跳过。覆盖原有资料、备份、规则与界面，新增 Mac 导航、搜索、菜单角色、关闭 / 重新显示、窗口记忆、退出保护及权限降级。
- 原生 Cocoa 环境打开首页、资源库、工具、图片、字体、色板、换算、设置、帮助；检查 1180×800 和 1020×720 两种尺寸，共 18 张页面截图。
- 原生搜索弹窗通过键盘回车打开真实字体页；实际列出本机字体。
- 验证记录在 `artifacts/mac-tests-final.log`、`artifacts/mac-specific-tests.log`、`artifacts/mac-native-smoke.log` 与 `artifacts/mac-review/`。这些是本地产物，不纳入版本控制。

自动化的 Dock 重开测试模拟 Qt 激活事件；仍需结合实际 Dock 点击、多个显示器、不同系统缩放及 VoiceOver 做人工验收。当前未做 Intel 构建或其他系统版本的真机验收。

## 实现入口

- `mac_workspace.py`：首页和命令搜索，复用工具目录，不预读资源。
- `mac_desktop.py`：原生菜单角色、窗口行为、快捷键和本地布局记忆。
- `ui.py` / `theme.py`：Mac 侧栏、工具栏与主题；Windows 保留原有入口布局。
- `platforms/macos.py`：先查权限，再查询输入状态。
- `app.py`：系统字体、安全预览、截图时使用无按键后端。

0.10.1 在现有 Mac 外壳中加入 [项目规格与资源](PROJECTS.md)。上方 164 项验证为 0.9.0 的历史记录，项目版最新结果见该版本说明。
