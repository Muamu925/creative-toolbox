# Autosave Lite

macOS 菜单栏中的空闲自动保存工具。选定 Illustrator、Photoshop 或其他支持 ⌘S 的本地应用，每次打开时决定是否启用本次保护。软件在前台、文档可识别、输入停止后，Lite 会请求保存。退出目标软件即结束本次保护，登录 Mac 后自动启动可在设置中开启，默认关闭。

**本分支提供 0.1.2 源码预览。** 使用 Swift 与 AppKit 开发。最低部署目标为 macOS 13，本机回归环境为 Apple Silicon。[使用说明](autosave-lite/README.md) · [验证范围](autosave-lite/VALIDATION.md) · [跨平台工具箱与下载](https://github.com/Muamu925/creative-toolbox/tree/main)

## 从源码运行

在装有 Python 3 和配套 Swift 命令行工具的 Mac 上执行以下命令。

```sh
git clone --branch codex/autosave-lite --single-branch https://github.com/Muamu925/creative-toolbox.git
cd creative-toolbox
python3 autosave-lite/scripts/build.py --test
python3 autosave-lite/scripts/build.py
```

构建产物为 `dist/Autosave Lite.app`，使用本地临时签名。将应用放入「应用程序」再打开。需要安装镜像时，可运行 `python3 autosave-lite/scripts/build.py --package`。

## 开启本次自动保存

1. 点击「添加应用」，从运行中的程序选择目标，或手动选择 `.app`。在「系统设置 → 隐私与安全性」中授予辅助功能和输入监控权限，返回 Lite 点击「重新检查」，确认事件发送也已就绪。
2. 打开目标软件并选择「启用本次保护」。先手动保存一份测试文档，做一处可辨认的修改，让文档保持前台。默认最短保存间隔为 **60 秒**，还需连续空闲 **3 秒**。持续空闲期间只请求一次。
3. 等原软件完成保存后，关闭并重新打开测试文档核对修改。界面的「已发送 ⌘S」仅记录请求。两款工具同时运行时，为同一目标只启用一处自动保存。

## 崩溃后的恢复资料

Illustrator 或 Photoshop 退出后，Lite 可复制遗留的恢复资料并记录校验值。也可打开「崩溃抢救」手动保留资料，再由原应用恢复、另存新文件并核对最近编辑的内容。能够恢复到哪一次修改，取决于原应用实际写下的数据。[恢复操作](autosave-lite/README.md) · [设计与实现](docs/AUTOSAVE_LITE_PLAN.md) · [MIT 许可证](LICENSE)
