# 创作工具箱 · Creative Toolbox

创作工具箱为 Windows 和 macOS 上的创作软件提供**空闲自动保存**。为常用软件设置保存间隔和快捷键，当你停下键鼠操作、目标窗口仍在前台时，工具箱会请求当前软件保存文档。图片、字体、配色和项目整理是可按需使用的辅助工具。

[Windows 预览版（ZIP）](https://github.com/Muamu925/creative-toolbox/releases/download/v0.10.1/CreativeToolbox-0.10.1-Windows-x64.zip) · [Mac 预览版（Apple Silicon DMG）](https://github.com/Muamu925/creative-toolbox/releases/download/v0.10.1/CreativeToolbox-0.10.1-macOS-arm64-unsigned.dmg) · [Autosave Lite 源码](https://github.com/Muamu925/creative-toolbox/tree/codex/autosave-lite) · [English](README.en.md)

## 选择版本

| 版本 | 适用场景 | 获取方式 |
| --- | --- | --- |
| **Creative Toolbox** | 在 Windows 或 Mac 上按应用配置保存快捷键、间隔与提醒，同时使用创作辅助工具 | [0.10.1 预览版与校验文件](https://github.com/Muamu925/creative-toolbox/releases/tag/v0.10.1) |
| **Autosave Lite** | 在 Mac 菜单栏中使用空闲保存。每次打开所选软件时确认是否启用，退出该软件后结束本次保护。另可保留 Illustrator、Photoshop 遗留的恢复资料 | [0.1.2 独立源码分支与构建说明](https://github.com/Muamu925/creative-toolbox/tree/codex/autosave-lite) |

Windows 版需完整解压 ZIP，再运行其中的 `CreativeToolbox.exe`。Mac 版需将 DMG 中的应用拖入「应用程序」，当前镜像适用于 macOS 13 及以上的 Apple Silicon Mac，尚未公证。[Mac 安装与权限说明](docs/MACOS.md)

## 第一次设置自动保存

1. **先保存一份测试文档。** 在目标软件中新建文档，手动保存一次，确认该软件的保存快捷键。默认使用 Windows 的 **Ctrl+S** 或 macOS 的 **⌘S**。
2. **添加应用规则。** 打开工具箱的「创作保护 → 应用规则 → 添加应用」，选择目标程序，启用规则，并设定最短保存间隔和输入空闲时间。Mac 用户可在工具箱「设置」中查看辅助功能和输入监控权限。
3. **观察触发时机。** 工具箱每次启动都进入观察模式。切回目标文档，做一处可辨认的修改并停下操作，之后可在「活动记录」中查看规则是否触发。录音、演奏和渲染都可能在键鼠空闲时继续，适合在应用规则中选择「仅提醒」。
4. **开启并验证。** 在「保护状态」点击「开启自动保存」，回到测试文档再做一次修改。等待保存间隔和空闲时间都满足，再等原软件保存完成。关闭并重新打开测试文档，确认修改仍在。如果关闭时仍提示保存，可先取消关闭，检查规则与权限。

工具箱发送快捷键前会再次核对前台窗口和输入状态。同一次持续空闲只处理一次。「活动记录」中的保存请求表示快捷键已发出，文件写入由目标软件完成。若同时安装两个版本，请为同一软件只启用一处自动保存。

## 辅助工具

| 功能 | 用途 |
| --- | --- |
| 图片与配色 | 收集参考图、记录来源、关联色板、提取颜色和检查对比度。[图片素材库](docs/ASSET_LIBRARY.md) |
| 字体与换算 | 对照本机字体样张，换算尺寸、分辨率和节拍时值。[字体工作区](docs/FONT_WORKSPACE.md) · [工具指南](docs/WORKSPACE.md) |
| 项目与资源 | 记录项目规格、整理参考素材、导出 Markdown 说明，或备份工具箱内的资料。[项目指南](docs/PROJECTS.md) · [资料备份范围](docs/RESOURCE_SEARCH_BACKUP.md) |

## 开发与反馈

主分支维护跨平台工具箱，Lite 分支维护原生 macOS 菜单栏应用。报告保存问题时，请注明使用的版本、系统、目标软件，以及「活动记录」和重新打开文档后分别观察到的结果。[问题反馈](https://github.com/Muamu925/creative-toolbox/issues) · [开发与构建](docs/DEVELOPMENT.md) · [贡献指南](CONTRIBUTING.md) · [MIT 许可证](LICENSE)

<details>
<summary>GitHub Star 历史</summary>

[![Creative Toolbox 的 GitHub Star 历史](https://api.star-history.com/chart?repos=Muamu925/creative-toolbox&type=date&legend=top-left)](https://www.star-history.com/?repos=Muamu925%2Fcreative-toolbox&type=date)

</details>
