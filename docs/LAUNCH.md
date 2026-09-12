# 预览版试用与传播

先让真实用户顺利完成一次“下载 → 打开 → 悬浮色卡复制”，再扩大分享范围。Star 是反馈之一，也应关注下载、具体使用反馈和重复出现的问题。

## 首轮试用

- 邀请 5–10 位设计、剪辑或音乐创作者试用；分别记录系统、主要创作软件、安装是否成功、第一次复制色号是否顺利。
- macOS 优先补充真机安装、权限、置顶、全屏和切换应用的反馈。
- 先修复阻止试用的问题，再按重复出现的场景排序功能需求。
- 每周由维护者查看 GitHub 流量、Release 下载次数和新反馈；记录改动与分享日期，不把 Star 数量承诺为结果。

## 可修改的中文分享草稿（尚未发布）

我做了一个本地运行的小工具「创作工具箱」。画图或做视觉方案时，可以把项目配色卡悬浮在创作软件旁边，点一下复制色号，减少来回找颜色的操作。

目前支持色板收藏与排序、图片提色、PNG 色卡导出，还带有字体对照、对比度与尺寸 / BPM 换算。无需账号，图片提色在本机完成。项目代码采用 MIT。

Windows 便携预览版已经提供下载；macOS 仍是实验版，界面目前以中文为主。特别希望听听：你在日常创作中，哪个小操作最值得省掉？

项目与演示：https://github.com/Muamu925/creative-toolbox
下载：https://github.com/Muamu925/creative-toolbox/releases/tag/v0.2.0

## English sharing draft (not posted)

I built Creative Toolbox, a local desktop companion for creative work. Its floating palette keeps project colors beside your apps so you can click to copy a color value.

The preview includes favorites, image color extraction, PNG swatch sheets, font comparison and design calculators. No account is required. Project code is MIT licensed.

A Windows portable download is available. macOS is experimental, and the interface is currently primarily Chinese. I would appreciate feedback on the small repetitive tasks that interrupt your creative workflow.

Demo and downloads: https://github.com/Muamu925/creative-toolbox

## 重新生成真实界面演示

在开发环境、Windows 原生桌面中执行（仓库根目录）：

```powershell
$env:PYTHONPATH = (Get-Location).Path
python tools/capture_demo.py
python -m pip install Pillow
python tools/encode_demo.py
```

捕获脚本使用临时示例数据、测试后端与关闭的保存计时器。只操作工具箱自身控件，不控制其他创作软件；复制演示会短暂使用系统剪贴板，并在未被用户覆盖时恢复原内容。帧图在已忽略的 artifacts/demo-frames，发布用 GIF / PNG 在 assets/demo。Pillow 仅用于作者制作演示，不进入产品依赖。
