# 开发、构建与能力边界

[返回首页](../README.md) · [English](../README.en.md)

## 当前边界

这是通用快捷键初版，**“已发送保存请求”不代表已确认保存成功**。它不读取应用文档内容，不能可靠判断文档是否修改、是否首次保存、是否在全部自定义编辑状态中，也不能读取 DAW 的录音/MIDI 或剪辑软件的渲染状态。OS 键盘空闲不包括所有 MIDI 或数位板工作状态。

47 项自动化测试已通过，覆盖 Windows 原生状态读取、输入包构造、核心规则、配色库、颜色与尺寸计算和 Qt 界面；Windows 独立程序已通过启动与自身界面渲染检查。真实跨进程 Ctrl+S 的隔离测试中，系统曾接受输入，但未取得接收窗口确认；后续尝试又遇到前台焦点被切换，测试按规则取消。**目前不把真实编辑软件的自动保存标为已验证**，应先在可丢弃测试文件中试用。

macOS 已通过 GitHub 托管运行器上的构建和自动化测试，尚未完成真实用户环境的安装、权限与宿主软件交互验收。版本备份、项目素材归档、开机自启、云同步和各创作软件深度适配尚未实现。

## 开发运行

需要 Python 3.12 或以上。Windows 使用 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

工作区已准备好环境时，也可以右键运行 `启动开发版.ps1`；这个脚本使用工作区 `.runtime/user` 保存试用配置。

macOS：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

macOS 系统适配依赖 PyObjC，需要相应辅助功能和输入监控权限。自定义快捷键的非美式键盘布局需要单独验证。跨平台共用核心和界面，系统接口分别实现；Linux 当前不支持。

默认设置目录为 Windows 的 `%LOCALAPPDATA%/CreativeToolbox`，或 macOS 的 `~/Library/Application Support/CreativeToolbox`。可用 `--data-dir PATH` 指定其他目录。配置不保存自动模式开关；日志不保存文档标题或键入内容。

## 自动打包与下载

在 [GitHub Actions](https://github.com/Muamu925/creative-toolbox/actions/workflows/build.yml) 中，每次推送 main、提交 PR 或手动运行都会测试并构建 Windows ZIP 和 macOS DMG；构建成功后可在该次运行的 Artifacts 中下载。

推送与 `pyproject.toml` 版本一致的标签（例如 `v0.2.0`）后，两端构建均成功才会自动上传到 [Releases](https://github.com/Muamu925/creative-toolbox/releases)，并附带 `SHA256SUMS.txt` 校验文件。当前自动发布为预览版，安装包未签名或公证。macOS 文件名标注实际构建架构，不是 universal2。

维护者发布步骤：更新 `pyproject.toml` 中的版本号和版本说明，提交并推送代码，然后创建对应版本标签并推送。仅更新 main 不会发布新版本。

## 验证与构建

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build.py
```

在 macOS 使用同样的 Python 命令运行 `tools/build.py`，它生成 `.app` 和标为 unsigned 的 `.dmg`。每个目标系统分别构建；Mac 产物面向构建环境的架构，不能直接视为 universal2。面向其他用户正式发布前需另行签名、公证，并完成对应系统和软件版本的实际验收。

Windows 构建脚本会排除错误收集的私有 ICU 库，使 Qt 使用系统提供的兼容接口；此处理修复了“源码可运行、独立程序导入 QtCore 失败”的打包问题。

`tools/windows_smoke.py` 仅向自己创建的临时窗口尝试发送一次 Ctrl+S，并等待该窗口写入测试文件。它需要交互式 Windows 桌面；焦点或输入条件不符合时会取消，不会转而操作其他窗口。这个测试不会自动包含在单元测试中。

`--screenshot artifacts/preview.png` 只渲染工具箱自身界面并退出，用于界面检查。没有自动发布或上传行为。

## 目录

```text
creative_toolbox/
  design_core.py      配色库、色彩与设计计算
  design_ui.py        配色、换算与字体工具页面
  palette_model.py    主面板与悬浮窗口共享状态及撤销
  palette_widgets.py  悬浮色卡与 PNG 色卡导出
  core.py             保存规则、快捷键和状态模型
  controller.py       决策与发送协调
  storage.py          配置与本地日志
  platforms/          Windows / macOS 系统适配
  ui.py               桌面界面、应用规则和托盘
  app.py              启动入口与单实例锁
tests/                决策、原生结构和界面测试
tools/                打包与隔离测试
BRAINSTORM.md          产品与架构讨论
```

GitHub 仓库：[Muamu925/creative-toolbox](https://github.com/Muamu925/creative-toolbox)。

