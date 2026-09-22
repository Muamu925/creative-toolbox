# 创作工具箱 · 冷白与钴蓝

面向设计、剪辑与音乐创作者的本地桌面工作台。视觉要帮助用户找到工具、看懂输入和确认结果；图片、字体与配色都是同一工具箱中的内容。

## 设计来源与取舍

使用 Taste 的审阅方法与 designer-skills 中的视觉层级、设计 QA 原则，保留现有 PySide6 架构。

- [Apple Materials](https://developer.apple.com/design/human-interface-guidelines/materials)：材质主要用于导航与控制层，内容保持清晰。
- [Figma UI3 设计说明](https://www.figma.com/blog/our-approach-to-designing-ui3/)：区分导航、工具和内容区域，保留常用操作的文字标签。
- awesome-design-md 的 [Apple](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/apple/DESIGN.md)、[Figma](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/figma/DESIGN.md)、[Airtable](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/airtable/DESIGN.md)：借鉴中性色、留白、细边界和操作层级。这些是第三方网站分析，不是官方组件库。

`npx getdesign@latest add airtable` 因连接重置未安装成功；本轮直接阅读上游参考文件。Mobbin 当前未连接，没有使用或复制其页面。未引入 Apple/Figma 标志、专有字体或原生组件。

## 基础令牌

运行时的唯一主题定义在 `creative_toolbox/theme.py`。

| 用途 | 值 |
| --- | --- |
| 页面底色 / 内容表面 | #F3F5F9 / #FFFFFF |
| 主文字 / 辅助文字 | #202735 / #5C677A |
| 主操作 / 悬停 / 按下 | #245CDB / #194AB8 / #173D91 |
| 选中浅底 / 分隔线 | #EAF0FD / #DDE3EE |
| 风险操作文字 | #A33A35 |
| 字级 | 正文 13px，区域 16px，页面 26px，数字 30px |
| 圆角 | 输入 9px，按钮 10px，导航项 12px，工具行 16px，内容卡片 18px，强调面板 20px，导航容器 22px |
| 间距 | 以 4px 为基础，常用 8 / 12 / 16 / 20 / 24px；按平台文字作光学调整 |

平台字体为 Windows Microsoft YaHei UI、macOS PingFang SC；不随安装包再分发字体。真实字体预览保留用户选择的家族、字号与样式。图片和色号不随主题重新着色。正文、辅助文字和钴蓝文字在对应表面上的对比度至少为 4.5:1；装饰边界与不可用状态不计入此断言。

## 材质与性能

侧栏和顶部栏使用半透明渐变、细高光边界，在工具箱自己的冷白背景上形成玻璃近似效果。它不是原生 Liquid Glass，不读取桌面、不提供背景模糊或折射。内容列表、编辑器和帮助正文使用不透明表面。

设置 → 外观 → 减少透明效果，立即切换为不透明导航并移除背景光晕。偏好独立保存到 `appearance.json`，不影响保存规则或资源数据；损坏/未来格式保留原文件，只在本次窗口应用调整。写入失败必须明确提示。没有用于装饰的循环动画或额外定时器。

## 导航与操作

侧栏固定为首页、资源库、工具，以及创作保护、设置、帮助。图标配文字，当前页面使用浅蓝底；键盘焦点另有边框。页面切换不保留其他导航项的焦点描边。

首页把收集图片与浏览工具放在同一操作行；工具条目只保留中性“打开”和次级“收藏”，避免多个主按钮抢占注意力。创建、导入和明确的保存任务可使用钴蓝主按钮。顶部始终可查看保护状态和本页帮助。

输入具有持续标签或辅助技术名称；占位只作示例。按钮、输入、列表、页签、下拉框、数值框、复选框、菜单、弹窗采用统一状态。禁用不代表已完成，保存快捷键请求不等于确认文件写入。

## 资源与帮助

图片库保持左列表、右预览与元数据，详情可滚动，保存 / 置顶 / 回收站操作固定。集合筛选独立于待整理状态；备份与恢复为次级操作。长路径放入提示，避免撑宽窗口。

配色常用操作放在工具栏，文件交换集中于导入 / 导出；来源名称不撑宽窗口。字体批量操作随选择数量启用，2–4 项可用字体才可对照。字号较大时列表样张允许裁切，对照页提供完整的编辑预览。

帮助按任务组织，支持离线搜索、空结果指引与直接打开工具。首页指南、侧栏、顶部和 F1 使用同一份内容。

## 图标与分发

品牌图标为钴蓝收纳托盘与半透明创作面板，母版是本项目生成的图像，见 `assets/toolbox-master.png`。`tools/prepare_brand_assets.py` 从本地母版和 SVG 重新生成 PNG、Windows ICO 与 macOS ICNS，无需联网。

导航和控件使用 [Phosphor Regular](https://github.com/phosphor-icons/core) 同一图标家族，SVG 来源保留在 `assets/icons/`。MIT 声明在 `creative_toolbox/resources/PHOSPHOR-LICENSE.txt`，安装包另附许可证。运行时只加载 PNG，不增加 SVG 渲染依赖。

## 验收

使用隔离数据与不会发送按键的后端，检查 1180×800 和 1020×720 逻辑窗口。检查首页、搜索、资源入口、图片库、字体、色板、换算、保护、设置、帮助以及减少透明效果。检查按钮、选中、焦点、禁用、菜单与空状态。Windows 原生字体截图作为视觉依据；无头截图只用于辅助检查。macOS 仍需真机材质、缩放与交互验证。