# 换电脑开发交接文档

> 本文保留 2026-10-06 Windows 迁移时的盘点记录。当前版本、Mac 环境和发布状态以 [开发文档](DEVELOPMENT.md)、[Mac 说明](MACOS.md)及 [0.10.0 版本说明](releases/v0.10.0.md)为准。

整理日期：2026-10-06（香港时间）。适用于把当前工作区交给另一台电脑或另一位开发者继续开发。

[文档入口](README.md) · [开发文档](DEVELOPMENT.md) · [文件夹说明](PROJECT_FILES.md)

## 1. 交接结论与当前基线

这是本地运行的 Python + PySide6 桌面应用，产品名「创作工具箱 / Creative Toolbox」，工作区名「设计工具箱」。接手后先重建 Python 环境、重现当前测试和启动结果，再恢复个人资源数据并继续开发。

**需要分别带走源码、未跟踪的设计技能、用户资料备份。现有 `.venv` 不能直接在新电脑沿用，用户资料也不在项目文件夹内。**

| 项目 | 本次核对结果 |
| --- | --- |
| 源工作区 | `E:\codex\设计工具箱` |
| 当前代码版本 | `pyproject.toml`：0.8.0 |
| 当前分支 / HEAD | `main` / `65af611b3dad4a69e398dc43dbe990807565ae5d` |
| HEAD 记录 | 2026-09-26：资源统一检索与完整工作空间备份恢复 |
| origin | `https://github.com/Muamu925/creative-toolbox.git`；本次仅核对本机配置，未查询远端最新状态 |
| 写入本交接文档前的工作树 | 已跟踪文件无改动；`.agents/` 与 `skills-lock.json` 未跟踪 |
| 本次文档状态 | 新增交接 / 文件夹 / 文档索引，更新开发说明等；尚未提交或推送，要随文件夹一起复制 |
| 本机已验证环境 | Windows，64 位 Python 3.12.14；PySide6-Essentials / shiboken6 6.11.2；PyInstaller 6.22.2 |
| 当前真实用户目录 | `C:\Users\admin\AppData\Local\CreativeToolbox`，已确认存在 |
| 开发快捷脚本数据目录 | `.runtime\user`；盘点时尚不存在，运行脚本后会创建 |

本机 `.git` 的拥有者与读取账户不同，检查时使用了单次 `git -c safe.directory=E:/codex/设计工具箱 ...`。没有更改全局 Git 配置。如果新电脑遇到同类提示，确认目录属于自己迁入的项目后，只信任该项目路径。

## 2. 要带走哪些文件

| 内容 | 建议 | 原因 |
| --- | --- | --- |
| `creative_toolbox/`、`tests/`、`tools/` | 必带 | 代码、现有回归测试、打包 / 演示 / 验收工具 |
| `assets/`、`docs/`、`.github/` | 必带 | 图标母版和演示、开发知识、发布说明、自动构建配置 |
| 根目录说明与配置 | 必带 | `run.py`、启动脚本、两份 requirements、`pyproject.toml`、README 中英版、DESIGN、CONTRIBUTING、BRAINSTORM、LICENSE、`.gitignore` |
| `.git/` | 直接复制工作区时保留 | 保留本机提交、分支、标签和远端配置；隐藏目录需一起复制 |
| `.agents/skills/`、`skills-lock.json` | 必须单独确认已复制 | 当前未跟踪；仅 clone 不会带走。74 个技能不能只靠 13 条锁记录恢复 |
| 个人资料 `.ctbackup` | 要保留现有整理资料时必带 | 图片原件 / 集合、色板、字体整理、已保存设置 / 收藏 / 外观 |
| 字体文件与宿主工程 | 按实际需要另带 | 工具箱备份不含系统字体或 Photoshop / DAW 等宿主工程 |
| `.venv/` | 新电脑重建 | 配置引用旧电脑绝对 Python 路径；复制过去也不能视为可用环境 |
| `build/`、`__pycache__/` | 可省略 | 构建和 Python 缓存可以重建 |
| `dist/` | 开发可省略；最新包可单独归档 | 现有历史版本占约 605 MiB；只运行程序时需完整 ZIP / 整个程序目录 |
| `artifacts/` | 按需归档 | 截图、录制帧和验收记录；不是正式用户资源库 |
| `.runtime/` | 先筛选再决定 | 多为旧开发脚本、测试资料、日志、离线 wheels 和历史包；若今后 `.runtime/user` 有资料，应单独备份 |

本次盘点可重建或历史产物约占 1.2 GiB，其中 `.venv` 约 235 MiB、`.runtime` 269 MiB、`artifacts` 119 MiB、`build` 8 MiB、`dist` 605 MiB。数量会随开发变化，无需为继续开发全部复制。

### 直接复制工作区

最直接的方法是复制整个文件夹，显示隐藏项目并确认 `.git`、`.agents` 和本次新文档都在。新电脑仍需重建环境。若要减少体积，可用以下 Windows 示例复制源代码和项目资料；目标磁盘路径需换成实际迁移位置：

```powershell
$taskSource = 'E:\codex\设计工具箱'
$taskTarget = 'F:\迁移包\设计工具箱'
robocopy $taskSource $taskTarget /E /XJ /XD .venv .runtime build dist artifacts __pycache__ /XF *.pyc *.pyo /R:2 /W:1
if ($LASTEXITCODE -ge 8) { throw '复制存在失败，请检查输出并补齐文件。' }
```

上述示例不包含任何正式个人资料备份，也不包含 `.runtime` 内可能存在的试用资料。复制后检查目标中的新文档与技能，而不仅看源代码文件数量。Robocopy 的 0–7 返回值不一概表示失败；8 及以上需处理。

### 如果选择重新 clone

仓库 clone 可以恢复远端已提交代码，但远端当前 HEAD 本次未查询，本机只有部分历史标签也不代表全部发布版本。先核对新工作区版本和提交，再从旧工作区补入 `.agents/`、`skills-lock.json`、本次全部新增 / 修改文档、其他尚未提交改动以及独立用户备份。不要只 clone 完成后就认定交接完整。

## 3. 旧电脑：备份当前用户资料

本机已确认默认用户目录含 `assets/`、`appearance.json`、`events.jsonl`、`fonts.json`、`instance.lock`、`palettes.json`、`settings.json`、`workspace.json`。本次只确认目录与文件存在，没有导出或恢复真实个人资料。

推荐用应用现有的完整备份流程：

1. 在正在使用的工具箱中先保存需要保留的色板与整理信息，等待图片任务结束。
2. 到「资源库」，点击「完整备份」，保存 `.ctbackup` 到当前数据目录以外的迁移目录 / 移动磁盘。
3. 等待成功提示，再把该文件和源代码一起带到新电脑；保存一份原备份供回退。
4. 若还需历史活动日志或旧恢复副本，从系统托盘退出工具箱后，再另行复制其数据目录。关闭主窗口可能只是隐藏到托盘。

完整备份包含当前图片库原件、索引、集合、回收站，以及已保存的色板、字体整理、应用规则、工具收藏 / 最近使用和外观。它不包含字体文件、未保存编辑、活动日志、缓存、旧恢复目录、源代码或宿主工程。

图片页的 ZIP 备份只包含图片模块，不能代替完整 `.ctbackup`。大资料库导出 / 恢复还需要临时空间，原件累计上限为 5 GiB。

### 路径与手动复制注意点

Windows 默认位置是 `%LOCALAPPDATA%\CreativeToolbox`；macOS 为 `~/Library/Application Support/CreativeToolbox`。如果曾使用 `--data-dir`，以实际启动参数和设置中的「打开数据文件夹」为准。

「打开数据文件夹」打开当前活动目录；它可能不同于最初启动目录。完整恢复的 `active-workspace.json` 位于启动目录，图片单独恢复的 `asset-location.json` 位于活动目录。手动冷复制最初启动目录时，需要包含指针和全部被指向的子目录；只复制当前活动目录时，新电脑应明确用 `--data-dir <副本目录>` 启动。

手动复制数据库及原件前应退出所有使用该库的工具箱进程，复制整库和相关 JSON / 指针。单独复制运行中的一个 `.sqlite3` 不能作为完整资料备份。`instance.lock` 是运行状态文件，不需要作为资料保留；遇到占用提示先确认是否仍有实例，不要运行中删锁。

## 4. 新电脑：重建开发环境

### Windows 推荐流程

安装 Git 和 64 位 Python 3.12，并准备能安装 `requirements.txt` 依赖的网络或完整离线包。项目要求 Python ≥3.12；3.12 最接近当前验证环境。把迁移项目放在普通本地可写目录，以下命令均在项目根目录运行。

旧 `.venv` 若随整夹带来，先改名另存，或在不含旧 `.venv` 的迁移副本中操作，再创建新环境；不要直接把旧环境当成新电脑环境。

```powershell
python --version
python -c "import struct; print(struct.calcsize('P') * 8)"
git status --short
git rev-parse HEAD
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe run.py --data-dir .runtime\user
```

应看到 64 位架构、正确的源码基线和全部测试通过；未改测试时预期 156 项。此处使用独立开发资料目录，首次打开没有旧资料属于正常情况，接着执行下一节的恢复。

使用虚拟环境内 Python 的完整路径无需先激活环境。日常隐藏控制台启动可运行 `启动开发版.ps1`；需要看报错时使用终端启动。若启动脚本被本机策略阻止，终端运行 Python 入口即可。

只运行现有便携程序可完整解压 Windows ZIP，打开 `CreativeToolbox/CreativeToolbox.exe`；这不需要 Python，但 ZIP 是运行包，不能替代开发源代码。

`.runtime/wheels` 当前只见部分构建依赖，不包含完整运行依赖，不能当作已准备好的离线安装套件。需要离线迁移时，应在联网电脑另外收齐目标系统 / Python 架构对应的运行与构建依赖并验证。

### 若新电脑是 macOS

在 Mac 上安装 Git、Python 3.12，进入项目根目录：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -v
.venv/bin/python run.py --data-dir .runtime/user
```

macOS 条件依赖由 requirements 自动选择；Windows 专用适配测试会按平台跳过，应记录具体跳过项，不能把本次 Windows「156 项、无跳过」当作 Mac 的预期。实际权限与创作保护需真机检查。字体家族名、默认快捷键风格和应用标识按平台确认。Windows 便携程序不能在 Mac 上使用，包应在 Mac 上构建。Linux 当前不支持。

## 5. 新电脑：恢复资料和继续工作

1. 在选定资料目录启动工具箱，进入「资源库 → 恢复备份」，选择迁入的 `.ctbackup`。
2. 等待清单、大小、摘要、数据格式、图片数据库与原件校验完成。恢复写入新的 `workspace-restored-<ID>`，原资料保留。
3. 选择切换，程序退出后，以同样的启动参数重新打开。若迁到 `.runtime/user`，之后继续用该路径或开发启动脚本。
4. 在设置中打开数据文件夹，确认是恢复后的活动目录；抽查图片、集合、色板、字体整理和来源跳转。退出重启，再验证收藏和设置仍保留。
5. 需要的系统字体在新电脑自行安装；缺失字体的整理记录保留，但样张可能回退。自定义快捷键及应用规则重新确认，创作保护先保持观察模式。

恢复成功后若取消切换，恢复副本保留但当前库继续使用原资料。重新使用可再次从原备份恢复，或明确用 `--data-dir` 指向该副本。需要回到最初资料时，退出程序，备份启动目录，将其中 `active-workspace.json` 改名保留再重新打开；原目录不要提前删除。

开发验收使用用户资料的副本即可。原电脑、原目录和原备份保留到新电脑验收完成。

## 6. 本次交接验证记录

以下结果均在 2026-10-06 的当前电脑获得：

| 检查 | 结果 / 证据 | 能说明什么 |
| --- | --- | --- |
| 全量现有测试 | 156 项，11.573 秒，`OK`，无跳过；日志 `.runtime/handoff-tests-2026-10-06.log` | 当前环境的现有自动化回归通过 |
| 源码入口 | 独立目录 `.runtime/handoff-source-smoke`，退出码 0 | 源码能在本机启动、观察模式渲染首页并退出 |
| 本机现有独立程序 | 独立目录 `.runtime/handoff-package-smoke`，退出码 0 | 当前 `dist/CreativeToolbox/` 能在本机启动和生成自身截图 |
| 首页截图 | `artifacts/handoff-2026-10-06/source-startup.png`、`package-startup.png` | 本次独立检查使用的界面证据；属于可选迁移验收材料 |
| 本地 0.8.0 ZIP | 58,425,141 字节；SHA-256 见下方 | 可核对这一个本地历史包是否原样复制 |

```text
dist/CreativeToolbox-0.8.0-Windows-x64.zip
SHA256: F62FDEE551CFC7CC8E801FEBBD0C36D20CE193A69FE4E3B6AB0A72FB6562600D
```

此摘要仅针对本机这份 ZIP，不是远端 Release 的已验证摘要。未重新打包；本次新文档尚不在旧 ZIP 内，下一次构建会由 `tools/distribution.py` 收入 docs。

本次未执行真实用户资料迁移、真实创作软件 Ctrl+S、macOS 真机安装或远端 Actions / Release 检查。单元测试通过和自身窗口启动都不等于确认宿主文档已经保存。

## 7. 新电脑验收清单

- [ ] 当前工作区包含代码、tests、tools、assets、docs、`.github`、隐藏 `.git` 及本次交接文档。
- [ ] `.agents/skills` 74 个技能原件与 `skills-lock.json` 已带走；不依赖 lock 重建全部技能。
- [ ] 重建 `.venv`，依赖无冲突；记录 Python、PySide6 与系统版本。
- [ ] 全量测试通过；记录执行数、跳过数和实际输出。
- [ ] 独立开发目录可启动，首页、字体、配色、换算、图片与帮助可打开。
- [ ] `.ctbackup` 已恢复；抽查集合、色板来源、字体整理、收藏与设置，并验证重启保留。
- [ ] 系统字体、平台权限和应用规则已确认，保护启动为观察模式。
- [ ] 若需打包，已在目标系统构建，完整程序目录和 ZIP / DMG 可运行；旧验收包已另存。
- [ ] Git 推送所需登录在新电脑重新配置；如使用 Codex，已添加新本地项目并读取本文。
- [ ] 验收完成前原电脑及原备份保持可用。

## 8. 接手后的优先顺序

先完成上面的环境 / 数据迁移验收，固定新的基线，再开始功能开发。当前产品下一主线是从个人资料积累推进到项目组合与交付：项目规格卡、稳定资源引用、共享资料与项目副本，再接一种可追溯的图片输出流程。

以 [整体架构方案](ARCHITECTURE_PLAN.md) 的实施更新和阶段 C 为准，不重复开发已经在 0.4–0.8 完成的入口、图片库、搜索或完整备份。多图参考板、批量重命名、媒体引擎分别作为后续独立功能。

可以将下面的说明交给新电脑的开发者或 Codex：

> 请继续开发创作工具箱。先阅读 docs/HANDOFF.md、docs/PROJECT_FILES.md、docs/DEVELOPMENT.md 和 DESIGN.md，核对 0.8.0 / 65af611 的交接基线及工作树。重建虚拟环境、运行现有测试，使用独立 --data-dir 验证启动与恢复。保持每次启动观察模式、按需创建工具、图片和色板来源关联、旧资料损坏保护及完整备份可恢复。按 ARCHITECTURE_PLAN.md 的最新实施更新推进下一项明确任务；项目稳定引用等仍是待实现内容。
