import AppKit
import UniformTypeIdentifiers

final class PanelBackground: NSView {
    override var isOpaque: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill(); bounds.fill()
    }
}
final class FlippedView: NSView { override var isFlipped: Bool { true } }

final class ApplicationPicker: NSObject, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate {
    let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 520, height: 440),
                        styleMask: [.titled, .closable], backing: .buffered, defer: false)
    let search = NSSearchField()
    let table = NSTableView()
    let message = NSTextField(wrappingLabelWithString: "")
    let add = NSButton(title: "添加应用", target: nil, action: nil)
    let selected: Set<String>
    let completion: (DiscoveredApplication) -> Bool
    private(set) var all: [DiscoveredApplication] = []
    private(set) var filtered: [DiscoveredApplication] = []

    init(selected: Set<String>, completion: @escaping (DiscoveredApplication) -> Bool) {
        self.selected = selected; self.completion = completion
        super.init()
        panel.title = "选择自动保存应用"; panel.isReleasedWhenClosed = false
        panel.contentView = PanelBackground(frame: panel.contentView!.bounds)
        let root = NSStackView(); root.orientation = .vertical; root.spacing = 12; root.alignment = .leading
        root.translatesAutoresizingMaskIntoConstraints = false; panel.contentView!.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: panel.contentView!.leadingAnchor, constant: 20),
            root.trailingAnchor.constraint(equalTo: panel.contentView!.trailingAnchor, constant: -20),
            root.topAnchor.constraint(equalTo: panel.contentView!.topAnchor, constant: 18),
            root.bottomAnchor.constraint(equalTo: panel.contentView!.bottomAnchor, constant: -18)
        ])
        search.placeholderString = "搜索正在运行的应用"; search.delegate = self
        let refresh = NSButton(title: "刷新", target: self, action: #selector(reload))
        refresh.bezelStyle = .rounded
        let top = NSStackView(views: [search, refresh]); top.spacing = 10
        root.addArrangedSubview(top)
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("application"))
        column.width = 470; table.addTableColumn(column); table.headerView = nil
        table.rowHeight = 44; table.delegate = self; table.dataSource = self
        table.target = self; table.doubleAction = #selector(choose)
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.documentView = table
        scroll.borderType = .bezelBorder; root.addArrangedSubview(scroll)
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 230).isActive = true
        message.font = .systemFont(ofSize: 12); message.textColor = .secondaryLabelColor
        message.maximumNumberOfLines = 3; root.addArrangedSubview(message)
        let manual = NSButton(title: "选择应用文件…", target: self, action: #selector(manualSelection))
        let cancel = NSButton(title: "取消", target: self, action: #selector(close))
        for b in [manual, cancel, add] { b.bezelStyle = .rounded }
        cancel.keyEquivalent = "\u{1b}"; add.target = self; add.action = #selector(choose)
        let spacer = NSView(); let bottom = NSStackView(views: [manual, spacer, cancel, add]); bottom.spacing = 10
        root.addArrangedSubview(bottom)
        for v in [top, scroll, message, bottom] { v.widthAnchor.constraint(equalTo: root.widthAnchor).isActive = true }
        reload()
    }
    func begin(for parent: NSWindow) { parent.beginSheet(panel) }
    @objc func close() { panel.sheetParent?.endSheet(panel); panel.orderOut(nil) }
    @objc func reload() {
        all = ApplicationDiscovery.candidates(ApplicationDiscovery.running())
        applySearch()
    }
    func applySearch() {
        filtered = ApplicationDiscovery.candidates(all, query: search.stringValue)
        table.reloadData(); add.isEnabled = false
        message.stringValue = filtered.isEmpty ? "没有符合条件的运行应用。可刷新列表或选择 .app 文件。" : "应用选择无需保存权限；每次启动仍需确认是否启用。"
    }
    func controlTextDidChange(_ obj: Notification) { applySearch() }
    func numberOfRows(in tableView: NSTableView) -> Int { filtered.count }
    func tableViewSelectionDidChange(_ notification: Notification) {
        add.isEnabled = table.selectedRow >= 0
        if table.selectedRow >= 0 {
            add.title = selected.contains(filtered[table.selectedRow].id) ? "查看已添加应用" : "添加应用"
        }
    }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let app = filtered[row]
        let icon = NSImageView(); icon.image = NSWorkspace.shared.icon(forFile: app.path)
        icon.widthAnchor.constraint(equalToConstant: 28).isActive = true
        icon.heightAnchor.constraint(equalToConstant: 28).isActive = true
        let title = NSTextField(labelWithString: app.name + (selected.contains(app.id) ? " · 已添加" : ""))
        let subtitle = NSTextField(labelWithString: app.id); subtitle.font = .systemFont(ofSize: 10); subtitle.textColor = .secondaryLabelColor
        let labels = NSStackView(views: [title, subtitle]); labels.orientation = .vertical; labels.alignment = .leading; labels.spacing = 2
        let row = NSStackView(views: [icon, labels]); row.spacing = 8
        row.setAccessibilityLabel(title.stringValue)
        return row
    }
    @objc func choose() {
        guard filtered.indices.contains(table.selectedRow) else { return }
        let candidate = filtered[table.selectedRow]
        guard ApplicationDiscovery.running().contains(where: { $0.session?.key == candidate.session?.key }) else {
            message.stringValue = "该应用已退出，请刷新列表或选择应用文件。"; return
        }
        if completion(candidate) { close() } else { message.stringValue = "设置未能保存，请检查设置窗口中的原因。" }
    }
    @objc func manualSelection() {
        let picker = NSOpenPanel()
        picker.title = "选择需要自动保存的应用"; picker.prompt = "添加应用"
        picker.directoryURL = URL(fileURLWithPath: "/Applications", isDirectory: true)
        picker.allowedContentTypes = [.applicationBundle]
        picker.canChooseDirectories = false; picker.canChooseFiles = true
        picker.treatsFilePackagesAsDirectories = false
        picker.beginSheetModal(for: panel) { [weak self] response in
            guard let self, response == .OK, let url = picker.url else { return }
            do {
                let app = try ApplicationDiscovery.fromBundle(url)
                if self.completion(app) { self.close() }
                else { self.message.stringValue = "设置未能保存，请检查设置窗口中的原因。" }
            } catch { self.message.stringValue = error.localizedDescription }
        }
    }
}
