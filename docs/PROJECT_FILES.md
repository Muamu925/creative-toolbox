# 文件夹与内容说明

> 本文保留 2026-10-06 Windows 迁移时的盘点记录。当前版本、Mac 环境和发布状态以 [开发文档](DEVELOPMENT.md)、[Mac 说明](MACOS.md)及 [0.10.0 版本说明](releases/v0.10.0.md)为准。

整理日期：2026-10-06；基于 0.8.0 本机工作区盘点。

[文档入口](README.md) · [开发文档](DEVELOPMENT.md) · [换电脑交接](HANDOFF.md)

## 1. 工作区全貌

```text
设计工具箱/
├─ creative_toolbox/      产品源码和运行图标
├─ tests/                 现有自动化回归测试
├─ tools/                 构建、截图、演示、基准及隔离验证脚本
├─ assets/                图标母版、SVG 源图、发行图标和正式演示
├─ docs/                  开发、使用、架构、交接和历史版本说明
├─ .github/               持续构建与问题模板
├─ .agents/skills/        本地项目设计技能，当前尚未跟踪
├─ .git/                  本地 Git 提交、分支和仓库配置
├─ .venv/                 旧电脑 Python 虚拟环境，迁移时重建
├─ .runtime/              历史开发材料、日志、测试数据、部分离线依赖
├─ build/                 PyInstaller 生成文件
├─ dist/                  独立程序目录和历史版本 ZIP
├─ artifacts/             界面截图、录制帧、验收包和其他生成材料
└─ __pycache__/           Python 缓存
```

前三类源码目录、正式 assets 和 docs 是持续维护内容；生成目录已列入 `.gitignore`。用户实际资料通常在项目外的系统应用数据目录，不能从这张树判断资料已经备份。

## 2. 根目录文件

| 文件 | 内容 / 维护方式 |
| --- | --- |
| `run.py` | 调用 `creative_toolbox.app.main` 的简短开发 / 打包入口 |
| `启动开发版.ps1` | 使用 `.venv/Scripts/pythonw.exe`，从项目根启动，数据落 `.runtime/user` |
| `pyproject.toml` | 包名、版本、Python 要求、兼容依赖、GUI 命令、运行资源打包声明 |
| `requirements.txt` | 实际开发运行依赖；Qt 固定版本，macOS PyObjC 为条件依赖 |
| `requirements-build.txt` | PyInstaller 与构建工具版本 |
| `.gitignore` | 排除环境、缓存和构建 / 验收产物；没有排除 `.agents` 和技能 lock |
| `skills-lock.json` | 13 项 Taste 技能来源与校验记录；不是 Python 依赖锁，也不是全部技能清单 |
| `README.md`、`README.en.md` | 中英文产品说明、当前功能、下载、限制和参与入口 |
| `DESIGN.md` | 冷白与钴蓝视觉体系、主题、文字和交互规则；UI 修改先读 |
| `CONTRIBUTING.md` | 行为改动测试、平台验证和协作约定 |
| `BRAINSTORM.md` | 早期产品讨论与技术判断，保留历史背景 |
| `LICENSE` | 项目代码 MIT 许可证；不替代依赖、图标及参考材料自己的许可证 |

## 3. 产品源码逐项说明

下列路径均在 `creative_toolbox/` 下。

| 文件 / 子目录 | 主要内容 |
| --- | --- |
| `__init__.py` | Python 包声明与运行界面版本常量 `__version__`；发布时与 pyproject 版本同步 |
| `app.py` | Qt 启动、参数、活动空间解析、锁、后端、窗口、截图和定时退出 |
| `ui.py` | 主窗口、侧栏、托盘、规则弹窗、设置、日志、工具创建 / 退出和资源跳转 |
| `workspace.py` | `Tool` 注册表、内置工具工厂、关键词检索、收藏和最近使用存储 |
| `workspace_ui.py` | 首页、资源入口和工具目录界面 |
| `core.py` | 目标应用、快照、快捷键、保存策略和纯逻辑决策 |
| `controller.py` | 状态捕获、决策、发送前复核和观察 / 提醒 / 自动模式协调 |
| `storage.py` | 系统默认数据目录、规则预设、settings JSON 和活动日志 |
| `platforms/__init__.py` | 按系统载入适配器并处理不可用情况 |
| `platforms/windows.py` | Windows 前台 / 输入空闲与键盘原生接口 |
| `platforms/macos.py` | macOS 应用状态、输入与权限相关 PyObjC 适配 |
| `platforms/unavailable.py` | 可解释降级对象，停止按键能力但允许其他工具使用 |
| `design_core.py` | HEX / RGB / HSL、对比度、配色校验、尺寸 / PPI / 比例 / BPM 换算 |
| `design_ui.py` | 配色与创作换算页面，以及相关输入、复制和导出操作 |
| `palette_model.py` | 配色共享模型、选中 / 收藏 / 排序、复制偏好、20 步内存撤销、图片来源 |
| `palette_widgets.py` | 色卡控件、悬浮面板和 PNG 色卡导出 |
| `image_processing.py` | 图片颜色处理与提色辅助 |
| `fonts/library.py` | 字体整理 JSON、分组 / 标签 / 收藏 / 备注、校验与备份合并 |
| `fonts/page.py` | 字体搜索、批量整理、预览和 2–4 栏真实样式对照 |
| `fonts/__init__.py` | 字体子包声明 |
| `assets/library.py` | 图片校验、原件托管、SQLite 索引、集合、回收站、图片 ZIP 备份与恢复 |
| `assets/jobs.py` | 图片后台任务，连接与任务生命周期按线程管理 |
| `assets/page.py` | 拖放 / 主动粘贴、列表 / 详情、来源整理、集合、置顶窗口和关联提色 |
| `assets/__init__.py` | 图片子包声明；不要与根目录静态 `assets/` 混淆 |
| `resources_search.py` | 已保存图片 / 色板 / 字体整理记录的只读检索及活动图片位置解析 |
| `resource_ui.py` | 统一搜索、结果打开、完整备份 / 恢复进度和写入屏障 |
| `workspace_backup.py` | `.ctbackup` 清单、快照、摘要校验、独立恢复和活动空间指针 |
| `theme.py` | 主题令牌、Qt 样式和表面绘制基础 |
| `appearance.py` | 减少透明 / 动态效果的设置和兼容读取 |
| `motion.py` | 页面快照过渡、导航动效、轻提示与关闭动效的处理 |
| `help_ui.py` | 离线上手、常见问题、F1 / 本页帮助和工具直达 |
| `resources/` | 应用实际读取的 PNG 图标与 `PHOSPHOR-LICENSE.txt` |

日常修改入口与数据格式契约见 [开发文档](DEVELOPMENT.md)，不要直接在 UI 层改写其他模块的 JSON / SQLite。

## 4. 测试目录

| 文件 | 主要覆盖 |
| --- | --- |
| `test_safety.py` | 保存决策、控制器、平台输入 / 状态、假后端与触发保护 |
| `test_ui.py` | 规则编辑、偏好保存和主窗口基础交互 |
| `test_design.py`、`test_palette_workflow.py` | 色彩 / 尺寸 / BPM 计算、配色持久化、主 / 悬浮共享与导出 |
| `test_fonts.py` | 整理数据、分组、备份、偏好和字体页面 |
| `test_workspace.py` | 注册 / 搜索、收藏重启、按需创建、失败重试和平台降级 |
| `test_assets.py` | 图片托管、校验、去重、回收站、图片备份恢复及限制 |
| `test_resource_flow.py` | 集合、升级、图片与色板来源关联、帮助等跨模块流程 |
| `test_resource_workflow.py` | 统一资源搜索、完整备份 / 恢复、活动目录切换与精确跳转 |
| `test_design_refinements.py`、`test_appearance.py` | 界面状态、外观兼容、主题图标与可读性相关检查 |
| `test_motion.py` | 页面过渡、减少动态效果、轻提示替换和失败反馈 |
| `__init__.py` | 测试包声明 |

统一入口为 `python -m unittest discover -v`。本次实测 156 项通过；这不是每个创作宿主软件的真机兼容结论。有的演示工具复用测试假后端，所以迁移开发工作区时保留 tests。

## 5. tools 脚本说明

| 脚本 | 输出或用途 |
| --- | --- |
| `build.py` | 目标系统 PyInstaller 构建，Windows 程序目录 / macOS APP 与 unsigned DMG |
| `package_windows.py` | 给现有 Windows 程序目录加入文档并压成版本化 ZIP |
| `distribution.py` | 收集根说明、完整 docs、演示、Python / Qt 等组件许可证与第三方声明 |
| `windows_smoke.py` | 自建临时接收窗口，尝试一次 Ctrl+S，确认自身测试文件写入；需交互式 Windows 桌面 |
| `benchmark_workspace.py` | 临时库下测首屏 / 首次字体页，`--offscreen` 仅作无显示诊断 |
| `prepare_brand_assets.py` | 从本地图标母版和 SVG 重建 PNG / ICO / ICNS；仓库根运行，使用 QtSvg |
| `capture_workspace.py` | 首页、工具、紧凑资源布局及保护不可用状态截图 |
| `capture_fonts.py` | 本机字体库和对照示例截图 |
| `capture_assets.py` | 图片收集、提色和置顶参考示例 |
| `capture_resource_flow.py` | 集合、关联色板、帮助导航的示例流程 |
| `capture_resource_search.py` | 0.8.0 资源搜索示例截图 |
| `capture_design_review.py` | 多页 1180×800 / 1020×720 尺寸与减少透明效果审阅 |
| `capture_motion.py` | 导航、切页、反馈和减少动态效果的录制帧 |
| `capture_demo.py` | 配色演示原始帧 |
| `encode_demo.py`、`encode_motion.py` | 编码演示 GIF，需要额外安装 Pillow；不属于产品运行依赖 |

优先从项目根运行 `python -m tools.capture_*`、`python -m tools.benchmark_workspace`；构建按开发文档使用脚本路径。截图脚本通常使用隔离示例资料和不发送按键的后端，但部分输出会写回 `assets/demo`，重新生成后应检查 Git 差异。

## 6. assets、文档、CI 与技能

### 静态资源

根目录 `assets/` 是正式静态资产：`toolbox-master.png` 为图标母版，PNG / ICO / ICNS 为展示与打包格式；`icons/` 存 Phosphor SVG 原图和来源说明；`demo/` 存首页和发行文档引用的 PNG / GIF。运行时真正读图的目录是 `creative_toolbox/resources/`。两处都要随开发源码保留。

第三方设计参考在 `docs/design-references/`：Apple、Figma、Notion 的静态设计分析与上游 MIT 许可证，供设计讨论参考，不是应用代码或这些产品的官方组件规范。

### 文档和历史

全量文档用途见 [文档入口](README.md)。当前开发资料以 DEVELOPMENT / HANDOFF 和 0.8.0 使用文档为准。架构方案正文有 v0.3.0 评审，文首实施更新记录后续完成状态；NEXT_STAGE_SPEC、FONT_MANAGER_SPEC 为未来草案；BRAINSTORM 的尚无远端等表述、LAUNCH 的 0.3 传播稿和各版本的测试数量均属于历史。

`docs/releases/` 依次保留 v0.2.0、v0.3.0、v0.4.0、v0.5.0、v0.6.0、v0.7.0、v0.7.1、v0.8.0 说明。历史文档中的 66 / 81 / 130 / 140 等测试数不是本次交接总数。

### 自动构建与问题入口

`.github/workflows/build.yml` 配置 main / PR / 手动 / 版本标签的双平台测试构建和标签发布。`.github/ISSUE_TEMPLATE/bug_report.yml` 与 `feedback.yml` 分别收集可复现故障和使用反馈。源码中的工作流配置不证明远端当前运行成功。

### 项目设计技能

`.agents/skills/` 实测有 74 个技能目录，均有 `SKILL.md`，用于 Codex 的设计研究、策略、界面与设计协作。它们不是应用依赖，普通 Python 运行不会加载这些文件。

历史安装记录见 [设计审阅](DESIGN_REVIEW.md)：Taste 系列 13 项来自 `Leonxlnx/taste-skill`，由 `skills-lock.json` 记录；另 61 项来自 `Owl-Listener/designer-skills/main`，涵盖 design-research 14、ux-strategy 12、ui-design 19、design-ops 9、designer-toolkit 7，未记录在该锁文件。新电脑需复制全部技能原件，lock 自身无法重建全部 74 项。技能需要的插件 / 工具可用性仍由新设备配置决定。

## 7. 本机生成目录如何处理

`.runtime` 内当前有历史开发 / 修复 / 发布辅助脚本、旧版本下载、构建 / 回归日志、临时审阅库、设计参考下载缓存、部分构建 wheel。它保留开发过程痕迹，但正式维护入口应使用 creative_toolbox、tests、tools 和 docs；不能从这里随便选择旧修复脚本重放到新版本。

`artifacts` 包含 `design-review`、`asset-review`、`resource-review`、演示 / 动效帧、历史发布验收包，以及本次 `handoff-2026-10-06` 启动截图。正式对外展示资源以 `assets/demo` 为准。

`dist` 当前保留 0.1.0–0.8.0 的 Windows ZIP 和独立程序目录，是历史产物；`build` 是构建生成材料；`.venv` 是旧机器环境；`__pycache__` 可再生。它们都不能代替源码或系统用户数据目录。

保留历史验收证据时按需另存。本次没有清理任何目录、提交 / 推送 Git、打包迁移归档或导出用户真实资料；操作步骤与验收边界均已列入 [交接文档](HANDOFF.md)。
