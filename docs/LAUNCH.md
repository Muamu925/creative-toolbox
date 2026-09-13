# 综合创作工具箱：试用与传播

更新：2026-09-13。对外主张与 README 一致：为设计、剪辑与音乐创作，把常用小工具放在一起。展示现有模块与规划方向时明确区分状态。

## 首轮试用

- 邀请 5–10 位不同领域创作者，记录系统、主要软件、安装结果，以及完成一个具体任务的障碍。
- 设计用户可尝试字体对照或尺寸换算；音乐用户可尝试 BPM 音符时长；色彩工具作为另一条独立体验。视频用户可试用现有通用换算并反馈需求，当前尚无专用媒体处理。
- 智能保存先观察触发时机，仅在可丢弃文档中试用；macOS 重点补充安装、权限、置顶、全屏与应用切换反馈。
- 后续演示按任务轮换：字体与尺寸、保存规则、色彩，再逐步加入已发布的新模块。单个模块演示注明范围。
- 每周由维护者查看 GitHub 流量、Release 下载与反馈，记录改动和分享日期。Star 是反馈之一，不承诺增长数量。

## 中文分享草稿（尚未发布）

我正在做「创作工具箱」：把设计、剪辑和音乐创作中经常需要的小工具，集中到一个本地桌面应用里。

当前 0.2.0 预览版已经有智能保存规则、字体对照、尺寸与 BPM 换算，以及悬浮色卡等色彩工具。下一步计划加入参考图画板、工具搜索、文件整理和更多音视频辅助功能。

工具可以独立使用，无需账号，项目代码采用 MIT。Windows 有便携下载；macOS 目前是实验版，界面以中文为主。想听听你工作中反复切换软件才能完成的那些小任务。

项目与最新功能：https://github.com/Muamu925/creative-toolbox
下载：https://github.com/Muamu925/creative-toolbox/releases/tag/v0.2.0

## English sharing draft (not posted)

I am building Creative Toolbox: local desktop utilities for the small tasks that come up across design, video editing and music creation.

The 0.2.0 preview includes per-app idle-save rules, font comparison, size and BPM calculators, and color tools. Reference boards, tool search, file organization and more media utilities are planned additions.

Tools work independently, no account is required, and project code is MIT licensed. A Windows portable download is available; macOS is experimental and the interface is currently primarily Chinese. What small task makes you switch apps repeatedly during creative work?

Project and downloads: https://github.com/Muamu925/creative-toolbox

## 重新生成真实界面演示

在开发环境、Windows 原生桌面中执行（仓库根目录）：

```powershell
$env:PYTHONPATH = (Get-Location).Path
python tools/capture_demo.py
python -m pip install Pillow
python tools/encode_demo.py
```

捕获脚本使用临时示例数据、测试后端与关闭的保存计时器。只操作工具箱自身控件，不控制其他创作软件；复制演示会短暂使用系统剪贴板，并在未被用户覆盖时恢复原内容。帧图在已忽略的 artifacts/demo-frames，发布用 GIF / PNG 在 assets/demo。Pillow 仅用于作者制作演示，不进入产品依赖。
