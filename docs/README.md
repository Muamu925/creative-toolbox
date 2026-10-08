# 开发与交接文档入口

更新：2026-10-09（北京时间）。当前源码版本：0.10.1。

本项目的文件夹名是「设计工具箱」，产品名称是「创作工具箱 / Creative Toolbox」。这是 Python + PySide6 桌面项目。

[Mac 重制版：启动、快捷键、构建与验收](MACOS.md)

## 换电脑时先读什么

1. [换电脑开发交接](HANDOFF.md)：当前基线、必须带走的内容、用户资料备份、新电脑配置与验收。
2. [文件夹与内容说明](PROJECT_FILES.md)：源代码、资源、文档、技能、缓存和安装包的用途。
3. [开发、构建与能力边界](DEVELOPMENT.md)：代码分层、运行命令、数据结构、修改入口和发布流程。

## 已实现功能的详细说明

| 文档 | 内容 |
| --- | --- |
| [项目首页](../README.md) / [英文首页](../README.en.md) | 当前版本、功能范围、下载与产品介绍 |
| [界面设计规范](../DESIGN.md) | 视觉风格、主题、文字、材质与交互约束 |
| [首页与工具](WORKSPACE.md) | 工具搜索、收藏、最近使用和页面按需加载 |
| [图片素材库](ASSET_LIBRARY.md) | 导入、托管、集合、来源、置顶、回收站与图片模块备份 |
| [字体工作台](FONT_WORKSPACE.md) | 字体整理、分组、样张与对照 |
| [资源搜索与完整备份](RESOURCE_SEARCH_BACKUP.md) | 跨资源检索、完整资料备份、恢复与切换 |
| [版本说明](releases/) | 0.2.0 至 0.10.1 的分阶段变更记录 |
| [贡献说明](../CONTRIBUTING.md) | 行为改动验证和协作约定 |

## 后续开发与历史参考

后续实施顺序以 [整体架构与发展方案](ARCHITECTURE_PLAN.md) 的实施更新和阶段安排为准；[功能路线](FEATURE_ROADMAP.md) 列候选功能，[专项方案](NEXT_STAGE_SPEC.md) 补充交互与验收草案。

[字体方案](FONT_MANAGER_SPEC.md)、[产品讨论](../BRAINSTORM.md)、[设计审阅](DESIGN_REVIEW.md)、[试用与传播](LAUNCH.md) 和 [设计参考](design-references/README.md) 保存历史背景。其中旧版本说明、早期任务列表和传播草稿不代表当前版本状态。

历史交接时 156 项测试通过；0.10.1 本机 Mac 验证为 181 项通过、2 项 Windows 专用测试跳过。具体环境、验证范围与剩余验收事项见 [交接文档](HANDOFF.md)。后续修改后应重新记录结果。

项目组合第一版见 [项目规格与资源](PROJECTS.md)。新增 `projects.sqlite3`（user_version 1），完整备份使用 SQLite backup API 获取快照。旧图片、色板和字体库格式不变。
