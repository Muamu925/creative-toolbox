# 创作工具箱 · Creative Toolbox

面向设计、剪辑、三维和音乐软件的本地桌面工具箱。当前版本 **0.2.0** 包含通用智能保存，以及配色工作台、创作换算和字体对照，使用 Python + PySide6。

## 立即试用 Windows 初版

打包完成后打开 `dist/CreativeToolbox/CreativeToolbox.exe`。整个 `CreativeToolbox` 文件夹需要一起保留，不能只复制其中的 EXE。用户无需安装 Python。

1. 启动后进入**观察模式**，不会发送任何按键。
2. 打开「应用规则」，点击「从前台应用添加」，在 5 秒内切到目标创作软件；也可以手动选择程序。
3. 设置保存间隔、输入空闲时间和保存快捷键。默认跟随系统，也可以逐应用覆盖。
4. 先手动保存创作文件，确认快捷键配置正确。观察工作状态，再按需开启本次自动保存。
5. 录音、演奏、回放或渲染时，使用「仅提醒」或「暂停」。关闭主窗口后可在托盘继续运行；托盘菜单的「退出」会完全停止程序。

随附预设默认关闭，程序名称与 Bundle ID 只是起点，不宣称对应软件已经验证兼容；实际添加方式能避免版本名称不同造成匹配失败。修改规则后回到观察模式，每次启动也始终从观察模式开始。

## 已实现

- 观察、自动、暂停三种运行状态；每应用另有仅提醒选项。
- 按程序身份匹配应用；Windows 支持完整 EXE 路径或精确文件名，macOS 使用 Bundle ID。
- 保存最短间隔、输入空闲阈值、前台窗口稳定检查和发送前复查。
- 检测可观测的按键按住、部分系统弹窗、文字输入控件、菜单和拖拽状态。
- 跟随系统、Ctrl+S、macOS Command+S、自定义组合键，以及每应用覆盖。
- 应用添加、编辑、启停、移除；从前台应用自动识别；快捷键录制。
- 原子写入本地设置、有限大小的本地活动日志、系统托盘入口。
- 输入或窗口变化取消发送；检测异常暂停；发送失败暂停该应用，避免连续重试。
- 消耗自己产生的输入时间戳，避免在无人操作时不断重复触发。

## 设计辅助工具

- **配色工作台**：按项目建立色板，编辑颜色名称与色号；点击色块复制 HEX / RGB / HSL。支持 JSON 整库导入追加和导出、复制 CSS 变量、生成互补 / 邻近 / 三等分配色。
- **图片提色**：选择本地图片，提取最多六个近似主色并生成新色板；不会上传或保留源图。
- **文字对比度**：输入文字色和背景色，实时预览并查看 WCAG AA / AAA 的文字对比结果。
- **创作换算**：毫米与像素互换、PPI、等比缩放；BPM 对应普通 / 附点 / 三连音时长。
- **字体对照**：两栏比较本机已安装字体，调整文案、字号、粗体并复制字体名称。

从左侧的「配色工作台」「创作换算」「字体对照」进入。颜色保存于数据目录中的 `palettes.json`，与自动保存设置独立。提色和对比度面向不透明 sRGB；不提供印刷色彩校样。字体预览可能发生系统字形回退。

研究来源、候选功能和下一步集成方案见 [功能地图与集成路线](docs/FEATURE_ROADMAP.md)。新增工具使用现有依赖独立实现，没有捆绑所参考的外部应用。

## 0.2.0：颜色随手用

1. 在「配色工作台」选择色板，点击「悬浮色卡」；也可以从托盘菜单打开。悬浮窗口可置顶、折叠，拖动标题栏可移动，关闭后可再次打开。
2. 在主窗口编辑颜色、切换色板或复制格式，悬浮窗口同步更新。可以复制带 / 不带 `#` 的 HEX、小写 HEX、RGB、RGB 纯数值和 HSL；「复制整板」逐行复制全部颜色。
3. 点击颜色卡片的收藏按钮，使用「仅收藏」筛选当前色板；左右箭头调整颜色顺序。筛选收藏时排序按钮停用，避免修改未显示颜色之间的位置。
4. 「撤销」可恢复最近 20 次色板修改，包含删除、排序、编辑和收藏；撤销记录仅限本次运行。收藏、颜色顺序、最后选择的色板和复制格式会保存到本机。
5. 「导出 PNG」输出当前色板的全部颜色，带完整名称、HEX 色号和 sRGB 配置，不受窗口大小或收藏筛选影响。

旧版配色 JSON 可直接读取。schema 1 新增可选的 `favorite` 和 `preferences` 字段；导入追加色板时保留本机复制偏好。图片导出采用临时文件提交，写入失败不会截断已有目标文件。

Windows 已检查悬浮窗口原生布局与独立程序启动。macOS 置顶、全屏空间以及多显示器切换仍需真机验收。

## 当前边界

这是通用快捷键初版，**“已发送保存请求”不代表已确认保存成功**。它不读取应用文档内容，不能可靠判断文档是否修改、是否首次保存、是否在全部自定义编辑状态中，也不能读取 DAW 的录音/MIDI 或剪辑软件的渲染状态。OS 键盘空闲不包括所有 MIDI 或数位板工作状态。

47 项自动化测试已通过，覆盖 Windows 原生状态读取、输入包构造、核心规则、配色库、颜色与尺寸计算和 Qt 界面；Windows 独立程序已通过启动与自身界面渲染检查。真实跨进程 Ctrl+S 的隔离测试中，系统曾接受输入，但未取得接收窗口确认；后续尝试又遇到前台焦点被切换，测试按规则取消。**目前不把真实编辑软件的自动保存标为已验证**，应先在可丢弃测试文件中试用。

macOS 适配代码及构建入口已加入，但尚未在 Mac 上运行，尚无经验证的 DMG。版本备份、项目素材归档、开机自启、云同步和各创作软件深度适配尚未实现。

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

## Star 增长历史

如果这个工具对你有帮助，欢迎点亮 Star。点击下方图表可查看详细增长历史。

<a href="https://www.star-history.com/?repos=Muamu925%2Fcreative-toolbox&amp;type=date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Muamu925/creative-toolbox&amp;type=date&amp;theme=dark&amp;legend=top-left" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Muamu925/creative-toolbox&amp;type=date&amp;legend=top-left" />
    <img alt="Creative Toolbox 的 GitHub Star 增长历史" src="https://api.star-history.com/chart?repos=Muamu925/creative-toolbox&amp;type=date&amp;legend=top-left" width="800" />
  </picture>
</a>

图表由 [Star History](https://www.star-history.com/) 提供，数据更新可能存在缓存延迟。
