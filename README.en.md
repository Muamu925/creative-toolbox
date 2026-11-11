# Creative Toolbox

Creative Toolbox provides **idle autosave** for creative applications on Windows and macOS. Choose an application, set a save interval and a keyboard shortcut, and the toolbox asks that application to save when its window is active and keyboard and mouse input has stopped. Image, color, font and project tools are available alongside autosave.

[Windows preview (ZIP)](https://github.com/Muamu925/creative-toolbox/releases/download/v0.10.1/CreativeToolbox-0.10.1-Windows-x64.zip) · [Mac preview (Apple Silicon DMG)](https://github.com/Muamu925/creative-toolbox/releases/download/v0.10.1/CreativeToolbox-0.10.1-macOS-arm64-unsigned.dmg) · [Autosave Lite source](https://github.com/Muamu925/creative-toolbox/tree/codex/autosave-lite) · [简体中文](README.md)

## Choose an edition

| Edition | When to use it | Availability |
| --- | --- | --- |
| **Creative Toolbox** | Configure shortcuts, idle thresholds and reminders per application on Windows or Mac, with optional creative tools | [0.10.1 preview downloads and checksums](https://github.com/Muamu925/creative-toolbox/releases/tag/v0.10.1) |
| **Autosave Lite** | Use idle saving from the Mac menu bar. Confirm protection when a selected app starts. Protection ends when it exits. Lite can also preserve recovery files left by Illustrator and Photoshop | [0.1.2 source branch and build instructions](https://github.com/Muamu925/creative-toolbox/tree/codex/autosave-lite) |

On Windows, extract the entire ZIP and run `CreativeToolbox.exe`. On Mac, drag the application from the DMG to Applications. The preview DMG targets Apple Silicon and macOS 13 or later and is unnotarized. The application interface is primarily in Chinese. [Mac installation and permissions](docs/MACOS.md)

## Set up and verify autosave

1. **Start with a test document.** Save it manually once and check the creative application's save shortcut. The defaults are **Ctrl+S** on Windows and **⌘S** on macOS.
2. **Add an application rule.** Under **创作保护 → 应用规则 → 添加应用**, select the application, enable the rule and set the minimum save interval and idle time. Mac users can check Accessibility and Input Monitoring in the toolbox settings.
3. **Observe a trigger.** The toolbox starts each session in observation mode. Make a visible edit, leave the document in front and stop typing or moving the mouse. Check **活动记录** for the event. For recording, performance or rendering, choose **仅提醒** to receive a reminder while work continues without keyboard or mouse input.
4. **Enable and verify.** Select **开启自动保存** under **保护状态**, edit the test document again and wait for both thresholds and the application's save operation to finish. Close and reopen the document to check the edit. If asked to save on close, cancel and check the rule and permissions.

The toolbox checks the foreground window and input again before sending the shortcut, and handles each continuous idle period once. An event in the log records a save request. The creative application handles the disk write. If both editions are installed, enable autosave for each target in only one of them.

## Companion tools

| Tools | Uses |
| --- | --- |
| Images and color | Collect references, record sources, link palettes, extract colors and check contrast. [Image library](docs/ASSET_LIBRARY.md) |
| Fonts and calculators | Compare installed fonts and convert dimensions, resolution and tempo. [Font workspace](docs/FONT_WORKSPACE.md) · [Tool guide](docs/WORKSPACE.md) |
| Projects and resources | Organize project specifications and references, export Markdown briefs or back up toolbox data. [Projects](docs/PROJECTS.md) · [Backup scope](docs/RESOURCE_SEARCH_BACKUP.md) |

## Development and feedback

The main branch maintains the cross-platform toolbox. The Lite branch maintains the native macOS menu-bar app. When reporting a save issue, include the edition, OS, target app, log event and what you found after reopening the document. [Issues](https://github.com/Muamu925/creative-toolbox/issues) · [Build guide](docs/DEVELOPMENT.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
