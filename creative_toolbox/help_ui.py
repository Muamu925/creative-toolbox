"""Offline task-based help. No network, disk indexing, or external-app actions."""
from dataclasses import dataclass
from html import escape
from .theme import TOKENS
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QPushButton, QSplitter


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    summary: str
    tool: str
    sections: tuple


TOPICS = (
    Topic("start", "第一次使用", "用一个小任务开始，无需账号或项目。", "assets", (
        ("先试哪一个？", "收集参考：打开图片素材库，导入一张 PNG / JPEG。\n选择字体：打开字体工作台，输入自己的标题，选 2–4 个字体比较。\n取用颜色：打开配色工作台，点击色块复制色号。\n计算尺寸：打开创作换算，输入毫米与 PPI，查看像素结果。"),
        ("怎样找到工具？", "首页显示收藏和最近使用；资源库集中图片、字体、配色；工具页支持名称和关键词搜索。工具可独立使用，不必开启智能保存。"),
        ("不懂当前功能时", "点击顶部「本页帮助」，或按 F1，直接查看当前页面说明。在侧栏「帮助」中可以搜索问题。帮助可离线使用。"),
        ("如何退出？", "关闭主窗口时，如有系统托盘，工具箱会继续运行。请从托盘菜单选择「退出」。素材任务进行中退出时会提示取消并等待结束。"),
    )),
    Topic("assets", "图片素材库", "收集 → 整理 → 找回 → 对照参考。", "assets", (
        ("导入与粘贴", "从首页「收集参考图片」进入。点击导入、拖入本地 PNG / JPEG，或点击「粘贴图片」。不会自动读取剪贴板。图片复制到本地素材库，原文件移动后仍可使用。重复收集保留独立记录，相同原件共用存储。"),
        ("名称、标签与待整理", "选择图片，填写名称、用逗号分隔的标签、来源或作者、备注，点击「保存整理」。勾选「已整理」后不再出现在待整理范围。切换图片、筛选或退出时，未保存内容会提示。"),
        ("集合怎样使用？", "在「管理集合」中新建集合，再从图片的「更多操作 → 加入 / 移出集合」勾选所属集合。一张图可以属于多个集合。在选定集合内导入或粘贴，会自动归入该集合。重命名不会丢失图片；移除集合仅取消归类关系。"),
        ("找图和置顶", "搜索匹配名称、标签、来源与备注，空格可分隔多个关键词；可同时按集合和全部 / 待整理 / 回收站筛选。双击图片或点「置顶查看」打开单图参考窗，可调整大小或取消置顶。"),
        ("从参考图保存配色", "选择图片，点击「更多操作 → 从图片创建色板」。预览最多 6 个近似主色、填写色板名，再保存。以后可从图片打开关联色板，也可从色板跳回来源图片。不会自动同步你之后修改的色号。"),
        ("支持范围", "单次 100 张，单张 50 MiB / 4000 万像素；最多 10000 条记录、5 GiB 已索引原件、200 个集合。回收站计入容量。预览最长边 1200 px，不用于印刷或像素校验。其他格式、多图画板和项目引用尚未提供。"),
    )),
    Topic("palettes", "配色与图片来源", "保存自己的颜色，并知道它们从哪里来。", "palettes", (
        ("复制与整理色号", "点击色块复制；上方可选择 HEX、RGB、HSL 等格式。颜色可命名、收藏和调整顺序；也可复制整板。撤销保留本次运行最近 20 次色板修改。"),
        ("两种提色入口", "配色页「图片提色」只提取颜色，不收集原图。素材库「从图片创建色板」会保留库 ID、图片 ID 和提色时的名称，支持双向跳转。算法从缩略图提取近似主色，忽略部分透明像素；不能替代印刷校样。"),
        ("如何回到来源图片？", "关联色板下方显示来源，点击「查看来源图片」。图片在回收站时会打开回收站中的原记录。若当前素材库不同、图片缺失或正在运行任务，会说明原因，色板仍可使用。来源名称是创建色板时的记录。"),
        ("导出和备份", "「导入 / 导出」支持配色库 JSON、CSS 变量、PNG 色卡。JSON 导出包含全部色板和图片来源标识，不包含原图。跨机器保留来源需同时备份恢复对应图片库。导入色板为追加，可能出现同名色板。"),
        ("新格式兼容性", "首次创建带图片来源的色板后，配色库使用 schema 2。新版本可读取旧配色库；旧版工具箱无法编辑新格式，请保留新版和独立备份。"),
    )),
    Topic("fonts", "字体工作台", "整理系统可用字体，比较自己的文案。", "fonts", (
        ("整理候选字体", "搜索本机字体；选择一个或多个字体后，可收藏、添加标签、加入分组。一个字体可以属于多个组。单选可看详情，选择 2–4 个可用字体后开启对照。"),
        ("比较效果", "输入自己的标题或正文，调整样张和字号，并选择字体实际提供的样式。缺少字形时系统可能用其他字体替代，不能据此确认该字体覆盖了全部文字。"),
        ("备份包括什么？", "字体 JSON 备份保存分组、标签、备注等整理信息，不包含字体文件。换电脑后按本机完整家族名匹配；不可用字体保留记录。"),
        ("还不支持什么？", "当前不安装、卸载或激活系统字体；不判断字体授权，不扫描未安装字体目录。首次打开需要枚举本机字体，字体较多时可能等待。"),
    )),
    Topic("calculators", "尺寸与节奏换算", "快速计算常用数值。", "calculators", (
        ("毫米、像素与 PPI", "选择转换方向，填写宽高与 PPI。字段单位随方向切换。结果用于尺寸估算，不改变图片文件，也不改变设计软件中的文档设置。"),
        ("等比缩放", "输入原始宽高和目标宽度，计算等比高度。请先确认所有长度使用相同单位。"),
        ("BPM 音符时长", "输入 BPM 并选择音符分母、普通 / 附点 / 三连音，得到毫秒时长。BPM 以四分音符为一拍；结果不读取 Cubase 等宿主的速度或传输状态。"),
    )),
    Topic("protection", "智能保存与观察模式", "先确认触发规则，再选择是否自动发送快捷键。", "protection", (
        ("第一次怎样设置？", "在创作保护的应用规则中配置目标应用、保存快捷键、输入空闲时间和最短间隔。每次启动默认观察模式，预设规则默认未启用。先观察触发时机，再用可丢弃文件试用。"),
        ("Win 和 Mac 的快捷键", "Windows 通常使用 Ctrl+S，macOS 通常使用 Cmd+S。可在设置中选择默认风格，也可在单个应用规则中覆盖或录制快捷键。仍应确认目标软件的实际设置。"),
        ("为什么没有自动保存？", "确认应用规则已启用且与目标进程精确匹配；观察模式不会发送按键，仅提醒规则也不会。持续输入、间隔未到、模态窗口、暂停或平台权限不可用，都可能阻止触发。请查看保护状态与活动记录中的原因。"),
        ("发送成功是否代表保存成功？", "不代表。工具箱只能记录保存快捷键请求，无法通用确认文件已写入磁盘，也不能普遍识别录音、MIDI、渲染或首次保存状态。音乐与剪辑场景建议先使用观察或提醒模式。"),
        ("macOS 为什么权限不足？", "检查系统隐私与安全中的辅助功能权限，以及系统实际提示的相关权限。授权后可重启工具箱再观察状态。DMG 是未签名实验版本，自动构建通过不能替代真机验证。"),
    )),
    Topic("backup", "数据、备份与恢复", "知道哪些数据被保存，以及怎样带走。", "assets", (
        ("数据放在哪里？", "默认保存在本机应用数据目录。设置中的数据目录入口可打开位置；素材页底部悬停可查看当前图片库目录。无需账号，图片和提色无需上传。日志不记录键盘输入内容。"),
        ("图片库备份", "「备份素材库」包含原图、整理信息、集合及回收站，带校验清单。恢复先校验并重建预览，成功后才切换到独立恢复目录，旧库保留。取消或失败不会覆盖当前库或已有备份。"),
        ("这是一键备份所有工具吗？", "不是。图片 ZIP 不包括配色、字体、应用规则或工具收藏。配色需另行导出 JSON，字体需另行备份。图片与关联色板分别备份，恢复相同图片库 ID 后可继续跳转。"),
        ("回收站和容量", "移到回收站可恢复，但不会释放磁盘空间。本版没有永久清空。旧恢复目录也会继续占用空间；确认备份完整前不要自行删除。"),
        ("升级与返回旧库", "首次升级 0.5 图片库会保留 before-collections.sqlite3 再升级索引。恢复产生的旧库继续留在数据目录。需要切回旧库的详细步骤见随安装包附带的 docs/ASSET_LIBRARY.md，操作前退出工具箱并备份整个数据目录。"),
        ("分享前检查", "图片备份包含原始图片、备注、来源和原始本地路径；配色 JSON 包含来源标识和提色时的图片名称。分享前请检查这些内容。"),
    )),
    Topic("settings", "窗口、设置与常见问题", "处理运行、数据和反馈问题。", "", (
        ("如何减少透明效果？", "在设置的「外观」中开启「减少透明效果」，导航和顶部栏会立即变为不透明表面。选择保存在本机。玻璃外观是工具箱内绘制的近似效果，不会读取或模糊桌面内容。"),
        ("关闭窗口后还在运行", "有系统托盘时，这是正常行为，方便后台观察与悬浮工具使用。从托盘重新打开或选择退出。"),
        ("工具页加载失败", "先重试该工具，并检查应用数据目录是否可写、磁盘空间是否充足。损坏或未来版本的数据不会被示例内容覆盖；先备份原文件再处理。"),
        ("主窗口能用，保护不可用", "系统保存适配失败时会禁用保护操作，图片、字体、配色和换算仍可使用。帮助入口也保持可用。"),
        ("如何反馈？", "记录系统、工具箱版本、操作步骤、预期结果和实际结果。仓库地址：https://github.com/Muamu925/creative-toolbox 。页面不会自动上传数据或发送反馈。"),
        ("平台范围", "Windows 提供便携 ZIP，完整解压后运行并保留整个目录。macOS 提供实验性 DMG，尚需真机验证。当前不支持 Linux。"),
    )),
)
TOPIC_BY_ID = {topic.id: topic for topic in TOPICS}


class HelpPage(QWidget):
    open_requested = Signal(str)
    home_requested = Signal()

    def __init__(self):
        super().__init__()
        self.current_topic = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("需要时，指路就在这里。")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("使用指南 · 常见问题 · 离线可用")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        row = QHBoxLayout()
        row.addWidget(QLabel("搜索帮助"))
        self.search = QLineEdit()
        self.search.setAccessibleName("搜索功能和常见问题")
        self.search.setPlaceholderText("例如：集合、备份、没有保存、快捷键")
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        layout.addLayout(row)
        split = QSplitter()
        self.topics = QListWidget()
        self.topics.setMinimumWidth(165)
        self.topics.setMaximumWidth(240)
        self.topics.setAccessibleName("帮助主题")
        split.addWidget(self.topics)
        self.article = QTextBrowser()
        self.article.setOpenExternalLinks(False)
        self.article.setOpenLinks(False)
        self.article.setAccessibleName("帮助正文")
        self.article.document().setDocumentMargin(16)
        split.addWidget(self.article)
        split.setSizes([190, 570])
        split.setChildrenCollapsible(False)
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("打开对应工具")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self.open_current)
        actions.addWidget(self.open_button)
        home = QPushButton("返回首页")
        home.setObjectName("secondary")
        home.clicked.connect(self.home_requested.emit)
        actions.addWidget(home)
        actions.addStretch()
        layout.addLayout(actions)
        self.search.textChanged.connect(self.filter_topics)
        self.topics.currentItemChanged.connect(self.show_article)
        self.filter_topics()

    def filter_topics(self):
        wanted = self.current_topic.id if self.current_topic else "start"
        words = self.search.text().casefold().split()
        self.topics.blockSignals(True)
        self.topics.clear()
        selected = None
        for topic in TOPICS:
            haystack = " ".join([topic.title, topic.summary, *(text for section in topic.sections for text in section)]).casefold()
            if all(word in haystack for word in words):
                item = QListWidgetItem(topic.title)
                item.setData(Qt.ItemDataRole.UserRole, topic.id)
                self.topics.addItem(item)
                if topic.id == wanted:
                    selected = item
        self.topics.blockSignals(False)
        if self.topics.count():
            self.topics.setCurrentItem(selected or self.topics.item(0))
        else:
            self.current_topic = None
            self.article.setPlainText("没有找到相关说明。\n试试更短的关键词，例如「集合」「备份」或「快捷键」。")
            self.open_button.setEnabled(False)

    def show_article(self, item, *_):
        if item is None:
            return
        topic = TOPIC_BY_ID[item.data(Qt.ItemDataRole.UserRole)]
        self.current_topic = topic
        parts = [f"<h1>{escape(topic.title)}</h1><p>{escape(topic.summary)}</p>"]
        for heading, text in topic.sections:
            parts.append(f"<h2>{escape(heading)}</h2><p>{escape(text).replace(chr(10), '<br>')}</p>")
        self.article.setHtml("<html><head><style>body{color:INK;font-size:14px;} h1{font-size:24px;color:INK;} h2{font-size:17px;margin-top:22px;} p{line-height:150%;}</style></head><body>".replace("INK", TOKENS["ink"]) + "".join(parts) + "</body></html>")
        self.article.verticalScrollBar().setValue(0)
        words = self.search.text().strip().split()
        if words:
            self.article.find(words[0])
        self.open_button.setEnabled(bool(topic.tool))

    def open_current(self):
        if self.current_topic and self.current_topic.tool:
            self.open_requested.emit(self.current_topic.tool)

    def show_topic(self, identifier):
        self.search.clear()
        identifier = identifier if identifier in TOPIC_BY_ID else "start"
        for index in range(self.topics.count()):
            item = self.topics.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == identifier:
                self.topics.setCurrentItem(item)
                self.show_article(item)
                break
