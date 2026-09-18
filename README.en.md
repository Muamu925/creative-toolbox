# Creative Toolbox

**Everyday utilities for design, video editing, and music creation — together on your desktop.**

A local desktop toolbox for small tasks across creative applications. The long-term direction is a shared workspace spanning preparation, creation, and delivery for graphic/UI design, video, 3D, and music workflows.

**Version 0.4.0 is an early preview.** It adds a home page, tool search, favorites and recent tools alongside configurable idle-save rules, font organization and comparison, design calculators, and color tools. Reference boards, project management, batch delivery, and media processing are planned, not implemented.

[**Download Windows 0.4.0 preview**](https://github.com/Muamu925/creative-toolbox/releases/download/v0.4.0/CreativeToolbox-0.4.0-Windows-x64.zip) · [All downloads / experimental macOS build](https://github.com/Muamu925/creative-toolbox/releases/tag/v0.4.0) · [简体中文](README.md) · [Roadmap (Chinese)](docs/FEATURE_ROADMAP.md)

## Available today

| Module | Implemented capabilities | When to use it |
| --- | --- | --- |
| **Home and tool access** | Search, favorites, recent tools, font/palette entry points and on-demand pages | Find a utility and continue working |
| **Creative safeguards** | Per-app save shortcuts, idle thresholds and intervals; observation, reminder and automatic modes | Assist saving during idle moments; every launch starts in observation mode |
| **Fonts and text** | Search installed fonts; groups, tags, favorites, notes and backup; custom samples and 2–4 font comparisons with available styles | Organize project candidates and compare typography |
| **Size and rhythm calculators** | Millimeters / pixels / PPI, proportional scaling, BPM-to-note durations including dotted and triplet values | Calculate output dimensions, proportions or delay settings |
| **Color and contrast** | Custom palettes, floating swatches, image colors, text contrast, JSON / CSS / PNG export | Reuse colors, check text/background combinations and share swatches |

Tools work independently, without creating a project or enabling automatic saving. No account is required. Palettes, app rules and activity metadata stay on your computer; image color extraction does not upload images. The interface is currently primarily Chinese.

## Try it in two minutes

1. Download and fully extract the Windows ZIP. Open `CreativeToolbox/CreativeToolbox.exe`. Keep the entire folder together. Python is not required.
2. Open a favorite from Home, or search in **工具** (Tools) for fonts, mm, BPM or colors. Favorite a tool to add it to Home.
3. For idle-save assistance, configure the target app and shortcut in **创作保护 → 应用规则** (Creative safeguards → App rules). Check timing in **保护状态** (Protection status) observation mode, then test with disposable files.

The main window can close to the system tray when available. Reopen or quit from the tray menu.

![Version 0.4.0 home and favorite tools](assets/demo/workspace-home.png)

See the [workspace guide (Chinese)](docs/WORKSPACE.md). The resource entry currently opens fonts and palettes; image collection is not implemented. The font and color screenshots below are from earlier versions; those capabilities remain available.

<details>
<summary>Font workspace example: groups, tags and comparison</summary>

![Font workspace with local fonts and sample project groups](assets/demo/font-library.png)

![Compare available font styles](assets/demo/font-compare.png)

Actual Windows UI with installed fonts and isolated sample metadata. Multi-select fonts to add them to groups, favorite them or apply tags. A font can belong to multiple groups. Organization is stored locally in fonts.json; JSON backups merge metadata and do not contain font files.

This version organizes system-available fonts. Uninstalled font folders and system activation are not implemented. Family matching uses the full local Qt family name; unavailable families retain their metadata. Missing glyphs may fall back to another font. See the [usage guide (Chinese)](docs/FONT_WORKSPACE.md).

</details>

<details>
<summary>Color module example: floating swatches, favorites and export</summary>

![Actual color-module workflow: float, choose a format, copy, favorite, export](assets/demo/palette-demo.gif)

Actual UI states with isolated sample data in a short looping sequence. This demo covers the color module.

Copy HEX with or without `#`, lowercase HEX, RGB, numeric RGB or HSL, plus entire palettes and CSS variables. Name, favorite, filter and reorder colors; undo the last 20 changes during the current session. Favorites, order, palette selection and copy format persist.

![Example exported PNG swatch sheet](assets/demo/palette-sheet.png)

</details>

## Where the toolbox is heading

These are planned capabilities, not features in the current downloads. Priorities may change with user feedback.

| Direction | Proposed additions |
| --- | --- |
| **Further access improvements** | Design / video / music filters and configurable quick access |
| **Personal resource library** | Image inbox, collections, tags, source records and floating references; connections to palettes and font metadata |
| **Projects and delivery** | Specification cards, resource references, project copies and image output; reference boards and batch naming follow later |
| **Video and motion** | Media information, timecode/frame calculations and frame extraction, followed by conversion |
| **Music and audio** | Tap Tempo, bar duration, pitch/frequency conversion and audio specification checks |
| **Text and productivity** | Uninstalled font folders, smart groups, glyph coverage checks, text cleanup and reusable snippets |

The first access-and-foundations stage is implemented. Next: **build a personal resource library → combine resources into projects and deliverables**. Tools remain usable independently. See the [architecture and development plan](docs/ARCHITECTURE_PLAN.md) for implementation order and acceptance criteria, and the [feature map](docs/FEATURE_ROADMAP.md) for candidate capabilities, currently in Chinese.

## Platform status

- **Windows x64:** portable ZIP. Standalone startup and native UI checked locally; built in GitHub Actions.
- **macOS:** experimental DMG, with architecture in the filename. Built in GitHub Actions; real-device installation, permissions, and creative-app interaction still need validation.
- **Linux:** not currently supported.

These preview packages are unsigned and not notarized. Sending a save shortcut is **not confirmation that a document was saved**. Recording, MIDI performance, rendering, first-time saves, and custom editor states cannot be detected universally. Start with observation/reminder mode and disposable test documents.

Color tools target opaque sRGB. Extracted colors are approximate and are not print proofs. Missing font glyphs may use system fallback fonts.

## Feedback and development

[Report a bug](https://github.com/Muamu925/creative-toolbox/issues/new?template=bug_report.yml) · [Suggest an improvement](https://github.com/Muamu925/creative-toolbox/issues/new?template=feedback.yml) · [Contributing](CONTRIBUTING.md)

Requires Python 3.12+ for development:

```sh
python -m venv .venv
# Activate the virtual environment for your platform, then:
python -m pip install -r requirements.txt
python run.py
python -m unittest discover -v
```

There are 81 automated tests for save rules, font organization, palette persistence, floating-window synchronization, calculations, workspace navigation and graceful degradation. Tests do not replace validation in real creative applications.

[Detailed development notes (Chinese)](docs/DEVELOPMENT.md) · [Feature roadmap (Chinese)](docs/FEATURE_ROADMAP.md)

If this tool saves you a few app switches, a Star helps you find it again. Feedback about what still feels awkward is just as welcome.

## License

Project code is licensed under [MIT](LICENSE). Bundled third-party components, including Python and Qt / PySide6, retain their own licenses; their license files are included in the downloads.

