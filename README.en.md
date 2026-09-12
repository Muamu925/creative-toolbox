# Creative Toolbox

**Keep your palette beside your creative app. Click a color to copy it.**

A local desktop companion with floating palettes, image color extraction, font comparison, design calculators, and configurable idle-save rules.

[**Download Windows 0.2.0 preview**](https://github.com/Muamu925/creative-toolbox/releases/download/v0.2.0/CreativeToolbox-0.2.0-Windows-x64.zip) · [All downloads / experimental macOS build](https://github.com/Muamu925/creative-toolbox/releases/tag/v0.2.0) · [简体中文](README.md)

![Actual palette workflow: float, choose a format, copy, favorite, export](assets/demo/palette-demo.gif)

*Actual UI states with isolated sample data, presented as a short looping sequence. The app interface is currently primarily in Chinese; this page provides English guidance.*

## Try it in two minutes

1. Download and fully extract the Windows ZIP. Open `CreativeToolbox/CreativeToolbox.exe`. Keep the entire folder together. Python is not required.
2. Select **配色工作台** (Palette workspace) in the sidebar. Start with the sample palette, or choose **图片提色** (Extract colors) to select a local image.
3. Click **悬浮色卡** (Floating palette), choose your copy format, and click a swatch. Paste into your creative app yourself. Use **置顶** to keep the panel on top, or **折叠** to collapse it.

The main window can close to the system tray when available. Reopen or quit from the tray menu. You do not need to enable automatic saving to use the color tools.

## What is included?

| Tool | What it does |
| --- | --- |
| Floating palettes | Copy HEX with or without `#`, lowercase HEX, RGB, numeric RGB, or HSL; stays in sync with the workspace |
| Palette library | Named palettes and colors, favorites, filtering, arrow-based reordering, 20-step session undo, JSON import/export, CSS variables |
| Image color extraction | Create a palette with up to six approximate dominant colors from a local image |
| PNG swatch sheets | Export the full palette with names, HEX values, and an sRGB profile |
| Text contrast | Preview foreground/background colors and check WCAG AA/AAA text contrast thresholds |
| Font comparison | Compare two installed fonts using your own text; adjust size and bold styling |
| Design calculators | Millimeters/pixels, PPI, proportional resizing, and BPM-to-note durations with dotted/triplet options |
| Idle-save rules | Configure save shortcuts, idle time, and intervals for selected apps; every launch begins in observation mode |

![Example swatch sheet exported by Creative Toolbox](assets/demo/palette-sheet.png)

Palettes, rules, and activity metadata stay on your computer. Image extraction does not upload your image. No account is required. Favorites, order, the selected palette, and copy format persist; undo history lasts for the current session only.

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

There are 47 automated tests for save rules, palette persistence, floating-window synchronization, undo, calculations, and PNG export. Tests do not replace validation in real creative applications.

[Detailed development notes (Chinese)](docs/DEVELOPMENT.md) · [Feature roadmap (Chinese)](docs/FEATURE_ROADMAP.md)

If this tool saves you a few app switches, a Star helps you find it again. Feedback about what still feels awkward is just as welcome.

## License

Project code is licensed under [MIT](LICENSE). Bundled third-party components, including Python and Qt / PySide6, retain their own licenses; their license files are included in the downloads.

