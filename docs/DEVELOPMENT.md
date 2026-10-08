# 开发文档：架构、运行与构建

[文档入口](README.md) · [换电脑交接](HANDOFF.md) · [文件夹说明](PROJECT_FILES.md) · [项目首页](../README.md)

更新：2026-10-08（北京时间）。源码版本 0.10.0；交接基线 `main` / `65af611b3dad4a69e398dc43dbe990807565ae5d`。本文按当前源码整理；路线和历史讨论另见架构方案。

Mac 0.9.0 新入口与验证见 [Mac 重制版](MACOS.md)。Mac 使用独立 `.venv-mac`，双击根目录 `启动 Mac 开发版.command` 即可运行。下文 0.8.0 为既有核心能力与交接记录。

## 项目定位和已完成内容

工作区文件夹叫「设计工具箱」，产品名称为「创作工具箱 / Creative Toolbox」。它是本地运行的 Python 桌面应用，界面使用 Qt / PySide6，图片索引使用标准库 SQLite，其余设置和整理信息主要使用 JSON。没有前端网页项目、独立网络后端或账号服务；开发主流程无需 Node.js。

0.8.0 已实现：首页与工具搜索 / 收藏、图片收集与集合、图片来源与关联提色、单图置顶、字体整理与对照、尺寸 / 节奏换算、配色与悬浮色卡、创作保护、离线帮助，以及图片 / 色板 / 字体整理的统一搜索和完整备份恢复。

项目规格卡、多图参考板、批量交付、音视频媒体处理、云同步、系统字体安装 / 激活仍是规划。当前资源关联已经连接图片与色板，但还没有项目所需的稳定色板 / 字体资源 ID。不要将路线图中的方案当成可用功能。

## 启动与代码分层

```text
run.py / creative-toolbox 命令
  → app.main：解析参数、创建 QApplication
  → resolve_workspace：从启动目录确定活动资料目录
  → Store + QLockFile：载入设置、按活动目录防止重复实例
  → load_backend：选择 Windows / macOS 系统适配或故障降级对象
  → MainWindow：导航、托盘、保护状态、工具生命周期
      → 内置工具注册表 → 首次打开创建页面，之后复用
      → 图片 / 字体 / 配色各自的界面、模型与存储
      → 资源统一搜索与完整备份服务
```

| 层 / 模块 | 主要文件 | 责任与改动边界 |
| --- | --- | --- |
| 应用入口 | `app.py`、根目录 `run.py` | 参数、活动目录、Qt 生命周期、单实例锁、截图与退出 |
| 窗口和工具入口 | `ui.py`、`workspace.py`、`workspace_ui.py` | 主导航、托盘、500 ms 保护轮询、工具注册、收藏 / 最近使用、页面按需创建 |
| 创作保护 | `core.py`、`controller.py`、`storage.py` | 快捷键解析、状态模型、触发决策、发送前复核、设置和事件记录 |
| 系统适配 | `platforms/` | Windows 原生接口、macOS PyObjC、不可用能力降级 |
| 图片资源 | `assets/library.py`、`assets/jobs.py`、`assets/page.py` | 托管原件、SQLite、集合、后台任务、预览与图片备份 |
| 字体 | `fonts/library.py`、`fonts/page.py` | 本机家族信息、整理数据、样张与多栏对照 |
| 配色与换算 | `design_core.py`、`design_ui.py`、`palette_model.py`、`palette_widgets.py`、`image_processing.py` | 计算、色板校验、共享模型、悬浮窗口、图片提色和导出 |
| 统一资源流程 | `resources_search.py`、`resource_ui.py`、`workspace_backup.py` | 三类只读检索、精确跳转、后台完整备份、独立恢复、目录切换 |
| 界面基础 | `theme.py`、`appearance.py`、`motion.py`、`help_ui.py`、`resources/` | 主题令牌、外观持久化、短动效、帮助内容与运行图标 |

表中路径均相对 `creative_toolbox/`；完整文件与脚本说明见 [文件夹说明](PROJECT_FILES.md)。

### 当前实现中需要保持的约定

- `workspace.py` 中的 `Tool`、`TOOLS`、`TOOL_BY_ID` 是内置注册表。页面工厂接收资料根目录；`MainWindow.ensure_tool` 首次创建后缓存到 `tool_pages`。当前没有外部 Python 插件加载系统。
- `platforms.load_backend` 初始化失败时返回 `UnavailableBackend`，停止按键能力，字体、配色和图片等本地工具仍可使用。
- `PaletteModel` 由主色板页与悬浮色卡共享。提交先持久化，成功后更新内存并通知；最近 20 步撤销仅在本次进程内保留。
- 图片后台任务与搜索 / 备份使用 Qt 线程；控件更新留在 GUI 线程。SQLite 连接属于创建它的线程，不跨线程共用连接。图片任务记录目前属于素材模块，尚无全局任务服务。
- 色板自身仍以列表和内容指纹定位；图片来源采用 `library_id`、`asset_id`、`hash`。字体记录以完整家族名称匹配。重命名、重排或跨电脑时不能把显示名称 / 数组位置当成永久资源 ID。

## 本地数据与存储契约

`launch_root` 是默认目录或 `--data-dir` 传入目录；`active_root` 是 `resolve_workspace` 得出的当前资料目录。首次使用二者相同；完整恢复切换后，活动目录可能位于启动目录的 `workspace-restored-<32位十六进制>` 子目录。

| 文件 / 目录 | 当前格式和用途 | 完整 `.ctbackup` |
| --- | --- | --- |
| `settings.json` | schema 1；应用规则、快捷键风格和自定义组合键 | 包含已保存内容 |
| `workspace.json` | schema 1；收藏和最多 12 项最近工具记录 | 包含 |
| `appearance.json` | schema 1；减少透明效果、减少动态效果 | 包含 |
| `palettes.json` | schema 1 / 2；色板、颜色、复制 / 显示偏好；默认 / 旧库为 1，从图片创建关联色板时升级为 2 并允许 `source_asset`；自身未 UUID 化 | 包含 |
| `fonts.json` | schema 1；UUID 分组、以完整家族名为键的整理记录、样张 / 字号偏好 | 包含整理信息，字体文件不包含 |
| 活动图片目录 `assets/` | `library.sqlite3`、`originals/`、`previews/`、`staging/`；SQLite `user_version=2` | 原件、索引、集合、回收站包含，预览恢复时重建 |
| `asset-location.json` | 相对名称指向 `assets-restored-<32位十六进制>` 图片恢复库 | 不直接打包指针；导出解析后打包活动图片库 |
| `active-workspace.json` | 启动目录中的相对活动空间指针 | 不包含；新电脑恢复切换时重新建立 |
| `events.jsonl` / `events.previous.jsonl` | 本机活动日志；不记录窗口标题或输入内容 | 不包含，需保留时单独归档 |
| `instance.lock` | 活动目录的单实例运行锁 | 不包含，不作为用户资料移植 |

图片 schema 2 包含 `meta`、`blobs`、`assets`、`tasks`、`collections`、`collection_assets`。图片库从 `user_version=1` 升级、加入集合结构前保留 `before-collections.sqlite3`。原件用内容摘要管理，资源记录使用稳定素材 ID。

当前素材限额定义在 `assets/library.py`：每图 50 MiB、4000 万像素、每批 100 项、最多 10000 项、原件累计 5 GiB、集合最多 200 个。支持 PNG / JPEG；改限额时同时检查导入、恢复校验与界面提示。

完整备份在应用级写入屏障下获取已保存 JSON 和 SQLite 快照，打包活动图片库、清单、大小与 SHA-256。它不包含未保存编辑、系统字体、日志、缓存、旧恢复目录和源代码。恢复只写新目录；验证通过后明确切换，退出重启生效。备份操作会回到观察模式，不重新开启自动保存。详见 [资源搜索与完整备份](RESOURCE_SEARCH_BACKUP.md)。

### 数据格式变更

为数据加字段时，同时更新读取校验器、写入、旧版迁移、导入 / 导出、备份与恢复、跨模块引用以及损坏 / 中断测试。旧格式需要预先备份；遇到未知格式或损坏时保留原文件并显示具体原因。不要让校验器默默丢掉新字段，也不要把 SQLite 事务理解为已经覆盖 JSON 和原件文件。

现有损坏保护存在模块差异：配色、字体、工作台和外观存储进入只读保护；`settings.json` 载入失败则警告并回落到禁用的预设规则，保留原文件，但用户下一次成功保存设置会替换原文件。排查时先留副本，不要误认为所有模块都采用同一种只读策略。

## 当前边界

这是通用快捷键初版，**“已发送保存请求”不代表已确认保存成功**。它不读取应用文档内容，不能可靠判断文档是否修改、是否首次保存、是否在全部自定义编辑状态中，也不能读取 DAW 的录音/MIDI 或剪辑软件的渲染状态。OS 键盘空闲不包括所有 MIDI 或数位板工作状态。

2026-10-06 重新运行全部 156 项自动化测试通过，另确认源码和本机现有 Windows 独立程序可启动并渲染首页。测试覆盖规则、存储、字体、配色、图片、统一搜索、完整备份恢复和 Qt 界面；界面测试采用 offscreen 与独立临时资料，不能代替原生视觉或真实宿主兼容验收。历史跨进程 Ctrl+S 隔离测试曾未取得接收窗口确认，并出现焦点条件不满足而取消的情况。**目前不把真实编辑软件的自动保存标为已验证**，应先在可丢弃测试文件中试用。

原有项目记录记载 macOS 曾通过 GitHub 托管运行器构建和测试；本次交接未重新查询远端构建，仍待真实用户环境的安装、权限与宿主交互验收。完整工具箱资料备份已实现；宿主文档版本备份、宿主工程素材归档、开机自启、云同步和各创作软件深度适配尚未实现。

## 开发运行

需要 Python 3.12 或以上。Windows 使用 PowerShell：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --data-dir .runtime\user
```

工作区已准备好环境时，也可以运行 `启动开发版.ps1`；这个脚本使用工作区 `.runtime/user` 保存试用配置，首次启动会创建目录。排查启动异常时用上述终端命令查看错误，脚本使用 `pythonw.exe` 隐藏控制台。默认启动 `run.py` 不传参数时使用电脑的正式用户资料目录。

本机核对环境为 Python 3.12.14、PySide6-Essentials / shiboken6 6.11.2、PyInstaller 6.22.2。运行依赖以 `requirements.txt` 为准，构建依赖以 `requirements-build.txt` 为准；`pyproject.toml` 中为包元数据与较宽的兼容范围。macOS 的 PyObjC 条件依赖使用下限而非完整锁定，不能宣称所有平台完全一致可复现。现有 `.venv/pyvenv.cfg` 指向旧电脑的 Codex Python 路径，换电脑必须重建。

macOS：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py --data-dir .runtime/user
```

macOS 系统适配依赖 PyObjC，需要相应辅助功能和输入监控权限。自定义快捷键的非美式键盘布局需要单独验证。跨平台共用核心和界面，系统接口分别实现；Linux 当前不支持。

默认设置目录为 Windows 的 `%LOCALAPPDATA%/CreativeToolbox`，或 macOS 的 `~/Library/Application Support/CreativeToolbox`。可用 `--data-dir PATH` 指定其他目录。配置不保存自动模式开关；每次启动都处于观察模式；日志不保存文档标题或键入内容。资源和源码分别迁移，具体做法见 [交接文档](HANDOFF.md)。

入口还支持 `--screenshot PATH`（生成自身界面截图并退出）和 `--quit-after N`（N 秒后退出）。本机启动检查可用独立目录，避免与正式资料混用：

```powershell
.\.venv\Scripts\python.exe run.py --data-dir .runtime\dev-smoke --screenshot artifacts\dev-startup.png
```

## 自动打包与下载

在 [GitHub Actions](https://github.com/Muamu925/creative-toolbox/actions/workflows/build.yml) 中，每次推送 main、提交 PR 或手动运行都会测试并构建 Windows ZIP 和 macOS DMG；构建成功后可在该次运行的 Artifacts 中下载。

工作流配置为：推送与 `pyproject.toml` 版本一致的标签后，两端构建均成功才自动上传到 [Releases](https://github.com/Muamu925/creative-toolbox/releases)，并附带 `SHA256SUMS.txt`。这描述仓库内工作流，不保证远端当前执行结果。自动发布为预览版，安装包未签名或公证；macOS 文件名标注实际构建架构，不是 universal2。

维护者发布步骤：同步更新 `pyproject.toml` 的版本号与 `creative_toolbox/__init__.py` 的 `__version__`，补充 `docs/releases/v<版本>.md` 并核对 README，完成回归和目标平台验收后提交、推送代码，再创建对应版本标签并推送。包版本取 pyproject，运行界面版本取 __version__，两者必须一致。仅更新 main 不会发布新版本。

## 验证与构建

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build.py
.\.venv\Scripts\python.exe tools\package_windows.py
```

Windows 的 `build.py` 生成 `dist/CreativeToolbox/`，`package_windows.py` 才生成带版本号的便携 ZIP，并收集分发文档。构建会重建生成目录，需保留的旧包提前另存。在 macOS 安装两组依赖后使用 `.venv/bin/python tools/build.py`，它生成 `.app` 和标为 unsigned 的 `.dmg`；macOS 不执行 Windows 打包脚本。每个目标系统分别构建；Mac 产物面向构建环境的架构，不能直接视为 universal2。面向其他用户正式发布前需另行签名、公证，并完成实际验收。

Windows 构建脚本会排除错误收集的私有 ICU 库，使 Qt 使用系统提供的兼容接口；此处理修复了“源码可运行、独立程序导入 QtCore 失败”的打包问题。

`tools/windows_smoke.py` 仅向自己创建的临时窗口尝试发送一次 Ctrl+S，并等待该窗口写入测试文件。它需要交互式 Windows 桌面；焦点或输入条件不符合时会取消，不会转而操作其他窗口。这个测试不会自动包含在单元测试中。

`--screenshot artifacts/preview.png` 只渲染工具箱自身界面并退出，用于界面检查。没有自动发布或上传行为。

## 继续开发时从哪里改

| 任务 | 首先阅读 / 修改 | 验证重点 |
| --- | --- | --- |
| 增加小工具与首页入口 | `workspace.py` 注册表、`workspace_ui.py`、`ui.py` | 搜索、收藏重启、首次创建与重复进入、页面失败可重试 |
| 修改配色、提色或悬浮窗口 | `design_core.py`、`palette_model.py`、`palette_widgets.py`、`design_ui.py` | 写失败不改变内存、主 / 悬浮同步、撤销、导出、来源跳转 |
| 修改字体整理 | `fonts/library.py`、`fonts/page.py` | 缺失字体保留、分组和偏好持久化、导入合并、真实样式对照 |
| 修改图片流程 | `assets/library.py`、`assets/jobs.py`、`assets/page.py` | 损坏文件、限额、去重、线程连接、取消、集合迁移、原件恢复 |
| 修改搜索和完整备份 | `resources_search.py`、`resource_ui.py`、`workspace_backup.py` | 部分模块损坏、过期结果、活动目录、取消不覆盖、指针切换重启 |
| 修改创作保护 | `core.py`、`controller.py`、`platforms/`、`storage.py` | 启动观察模式、焦点 / 空闲 / 间隔复核、权限失败和发送前检查 |
| 调整视觉、反馈或帮助 | `theme.py`、`appearance.py`、`motion.py`、`help_ui.py` | 两种窗口尺寸、减少透明 / 动态效果、键盘导航、错误反馈 |

建议顺序：先在独立测试目录重现任务，再改纯逻辑 / 存储和界面，运行与行为相关的测试及全量回归，完成原生界面检查，更新功能说明与版本记录。修改保存策略时保持与其他工具改动分开。

引入项目模块前，先按 [架构方案](ARCHITECTURE_PLAN.md) 设计稳定资源引用、数据迁移和项目副本语义，补充恢复与两个项目隔离验收；不要直接把当前色板下标保存为项目引用。

测试按功能分布在 `tests/test_*.py`；具体对应关系见 [文件夹说明](PROJECT_FILES.md)。本次验证证据和新电脑验收清单见 [交接文档](HANDOFF.md)。

GitHub 仓库：[Muamu925/creative-toolbox](https://github.com/Muamu925/creative-toolbox)。


## 已落地功能的专项开发说明

### 0.4.0 工具入口

详见 [工作台说明与验证记录](WORKSPACE.md)。首屏不创建字体、配色或换算页面；工具首次打开后复用。新增 workspace.json 与原有资源文件分开，保存适配失败返回不发送按键的降级对象。启动测量用 python -m tools.benchmark_workspace；截图用 python -m tools.capture_workspace。

### 0.7 视觉资源

主题令牌与 Qt 样式在 `creative_toolbox/theme.py`；导航材质只绘制应用内表面。外观偏好单独保存到 `appearance.json`，不修改智能保存或资源数据。

在仓库根目录运行 `python tools/prepare_brand_assets.py` 可从提交的母版和 Phosphor SVG 重建 PNG、ICO 与 ICNS，依赖开发环境已有的 PySide6.QtSvg，不需要联网。运行时只使用 PNG。PyInstaller 和 setuptools 都包含 `creative_toolbox/resources`，分发文档附带图标许可证。

界面审阅：`python -m tools.capture_design_review review-name`。本机默认使用原生 Qt 字体；无显示环境可明确设置 `QT_QPA_PLATFORM=offscreen`，但其字体渲染不可替代原生视觉验收。

### 0.7.1 动效与反馈

`creative_toolbox/motion.py` 提供页面快照过渡、导航选中动效和可替换的轻提示。所有动画均有限时长，支持立即关闭。不要在失败分支发出成功反馈；错误继续留在原页面。

录制：`python -m tools.capture_motion`。可选的 `python tools/encode_motion.py` 使用 Pillow 生成演示 GIF；Pillow 只用于文档作者，不是运行依赖。录制仅访问应用自己的窗口，使用独立临时数据，结束时会在剪贴板仍为演示结果的条件下恢复原内容。

项目组合第一版见 [项目规格与资源](PROJECTS.md)。新增 `projects.sqlite3`（user_version 1），完整备份使用 SQLite backup API 获取快照。旧图片、色板和字体库格式不变。
