import AppKit

final class RecoveryWindow: NSObject, NSTableViewDataSource, NSTableViewDelegate {
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 620),
                          styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
    let appPopup = NSPopUpButton()
    let table = NSTableView()
    let message = NSTextField(wrappingLabelWithString: "")
    let location = NSTextField(wrappingLabelWithString: "")
    let temporaryLocation = NSTextField(wrappingLabelWithString: "")
    let automatic = NSButton(checkboxWithTitle: "所选应用退出后，自动保留遗留恢复数据", target: nil, action: nil)
    let captureButton = NSButton(title: "检查并保留快照", target: nil, action: nil)
    let recordButton = NSButton(title: "记录另存文件…", target: nil, action: nil)
    let confirmButton = NSButton(title: "确认内容已恢复", target: nil, action: nil)
    let queue: DispatchQueue
    let serviceProvider: () -> RecoveryService
    let changeSettings: (Bool?, String?) -> Void
    let notify: (String) -> Void
    var snapshots: [RecoverySnapshot] = []
    var busy = false
    var selected: RecoverySnapshot? { snapshots.indices.contains(table.selectedRow) ? snapshots[table.selectedRow] : nil }

    init(queue: DispatchQueue, service: @escaping () -> RecoveryService,
         changeSettings: @escaping (Bool?, String?) -> Void, notify: @escaping (String) -> Void) {
        self.queue = queue; serviceProvider = service; self.changeSettings = changeSettings; self.notify = notify
        super.init()
        window.title = "Autosave Lite · 崩溃抢救"; window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 600, height: 600); window.center()
        window.contentView = PanelBackground(frame: window.contentView!.bounds)
        let root = NativeStyle.column([], spacing: 14)
        root.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 24),
            root.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -24),
            root.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 20),
            root.bottomAnchor.constraint(lessThanOrEqualTo: window.contentView!.bottomAnchor, constant: -20)
        ])
        let title = NSTextField(labelWithString: "崩溃抢救"); title.font = .systemFont(ofSize: 22, weight: .semibold)
        let description = NSTextField(wrappingLabelWithString: "先保留恢复资料，再使用原应用恢复并另存。")
        description.textColor = .secondaryLabelColor; description.font = .systemFont(ofSize: 12)
        root.addArrangedSubview(title); root.addArrangedSubview(description)
        for app in RecoveryDiscovery.supported { appPopup.addItem(withTitle: app.name); appPopup.lastItem?.representedObject = app.id }
        captureButton.target = self; captureButton.action = #selector(captureKnown)
        let manual = makeButton("保留文件或目录…", #selector(captureFolder))
        let captureRow = NSStackView(views: [appPopup, captureButton, manual]); captureRow.spacing = 10
        captureButton.bezelStyle = .rounded; root.addArrangedSubview(captureRow)
        automatic.font = .systemFont(ofSize: 12); automatic.target = self; automatic.action = #selector(toggleAutomatic)
        root.addArrangedSubview(automatic)
        location.font = .systemFont(ofSize: 10); location.textColor = .secondaryLabelColor
        location.maximumNumberOfLines = 2; location.isSelectable = true
        root.addArrangedSubview(location)
        let change = makeButton("更改快照位置…", #selector(changeLocation))
        let refresh = makeButton("刷新记录", #selector(refresh))
        let storage = NSStackView(views: [change, refresh]); storage.spacing = 10; root.addArrangedSubview(storage)
        temporaryLocation.font = .systemFont(ofSize: 10); temporaryLocation.textColor = .secondaryLabelColor
        temporaryLocation.maximumNumberOfLines = 2; temporaryLocation.isSelectable = true
        root.addArrangedSubview(temporaryLocation)
        root.addArrangedSubview(makeButton("打开系统临时目录", #selector(openTemporaryDirectory)))
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("snapshot")); column.width = 570
        table.addTableColumn(column); table.headerView = nil; table.rowHeight = 46
        table.dataSource = self; table.delegate = self
        let scroll = NSScrollView(); scroll.documentView = table; scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder; scroll.heightAnchor.constraint(equalToConstant: 160).isActive = true
        root.addArrangedSubview(scroll)
        message.font = .systemFont(ofSize: 12); message.textColor = .secondaryLabelColor; message.maximumNumberOfLines = 5
        message.heightAnchor.constraint(greaterThanOrEqualToConstant: 52).isActive = true
        message.stringValue = "暂无快照。请先检查恢复目录，或手动保留文件和目录。"
        root.addArrangedSubview(message)
        let reveal = makeButton("查看快照", #selector(revealSnapshot))
        recordButton.bezelStyle = .rounded; recordButton.target = self; recordButton.action = #selector(recordOutput)
        confirmButton.bezelStyle = .rounded; confirmButton.target = self; confirmButton.action = #selector(confirmOutput)
        let steps = NSStackView(views: [reveal, recordButton, confirmButton]); steps.spacing = 10
        root.addArrangedSubview(steps)
        let guide = makeButton("恢复操作说明", #selector(showGuide))
        let openHost = makeButton("打开所选应用", #selector(openApplication))
        let guideRow = NSStackView(views: [guide, openHost]); guideRow.spacing = 10
        root.addArrangedSubview(guideRow)
        for view in [description, location, temporaryLocation, scroll, message, steps] { view.widthAnchor.constraint(equalTo: root.widthAnchor).isActive = true }
        updateButtons()
    }
    func makeButton(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action); b.bezelStyle = .rounded; return b
    }
    func show(enabled: Bool) {
        automatic.state = enabled ? .on : .off
        refresh(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    @objc func refresh() {
        guard !busy else { return }
        let service = serviceProvider()
        location.stringValue = "快照位置：\(service.storage.path)"
        temporaryLocation.stringValue = "系统临时目录（自动识别）：\(RecoveryDiscovery.systemTemporaryDirectory().path)"
        queue.async {
            let values = service.snapshots()
            DispatchQueue.main.async {
                self.snapshots = values; self.table.reloadData()
                if !values.isEmpty { self.table.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false) }
                else { self.message.stringValue = "暂无快照。可检查已知恢复目录，或手动选择需要保留的恢复目录。" }
                self.updateButtons()
            }
        }
    }
    func updateButtons() {
        captureButton.isEnabled = !busy
        recordButton.isEnabled = !busy && selected != nil
        confirmButton.isEnabled = !busy && selected?.manifest.output != nil
    }
    func numberOfRows(in tableView: NSTableView) -> Int { snapshots.count }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let item = snapshots[row].manifest
        let title = NSTextField(labelWithString: "\(item.applicationName) · \(item.stage)")
        title.font = .systemFont(ofSize: 12, weight: .medium)
        let detail = NSTextField(labelWithString: "\(item.createdAt) · \(item.files.count) 个文件")
        detail.font = .systemFont(ofSize: 10); detail.textColor = .secondaryLabelColor
        return NativeStyle.column([title, detail], spacing: 3)
    }
    func tableViewSelectionDidChange(_ notification: Notification) {
        if let item = selected {
            message.stringValue = item.manifest.consistency == "verified"
                ? "文件副本与复制时的源文件已核对。请在原应用中完成恢复，另存新文件后再确认内容。"
                : "快照已保留，但存在读取失败或源文件变化。请查看 manifest.json 中的记录，不应视为完整可恢复备份。"
        }
        updateButtons()
    }
    @objc func toggleAutomatic() { changeSettings(automatic.state == .on, nil) }
    @objc func openTemporaryDirectory() {
        let directory = RecoveryDiscovery.systemTemporaryDirectory()
        if !NSWorkspace.shared.open(directory) {
            message.stringValue = "临时目录暂时无法打开，可复制上方路径在 Finder 中检查。"
        }
    }
    @objc func changeLocation() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.canCreateDirectories = true; panel.prompt = "选择位置"
        panel.message = "新快照将保存在所选位置的 Autosave Lite Rescue 子目录。已有快照不会移动。"
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else { return }
            self.changeSettings(nil, url.appendingPathComponent("Autosave Lite Rescue", isDirectory: true).path)
            self.refresh()
        }
    }
    @objc func captureKnown() {
        let id = appPopup.selectedItem?.representedObject as? String ?? ""
        let sources = RecoveryDiscovery.sources(for: id)
        capture(id: id, name: DesignApp.name(id), sources: sources)
    }
    @objc func captureFolder() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = true
        panel.prompt = "保留快照"; panel.message = "选择完整恢复目录或原设计文件，复制到新的快照。不改写或清理源数据。"
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else { return }
            self.capture(id: "manual", name: "手动恢复资料", sources: [RecoverySource(name: url.lastPathComponent, url: url)])
        }
    }
    @objc func openApplication() {
        guard !busy else { return }
        let id = appPopup.selectedItem?.representedObject as? String ?? ""
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id) else {
            message.stringValue = "未找到所选应用，请从 Finder 打开原应用。"; return
        }
        NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration()) { _, error in
            if let error { DispatchQueue.main.async { self.message.stringValue = error.localizedDescription } }
        }
    }
    func capture(id: String, name: String, sources: [RecoverySource]) {
        guard !busy else { return }; busy = true; updateButtons()
        message.stringValue = "正在保留完整目录并核对文件，请暂勿清理或移动源数据。"
        let service = serviceProvider()
        queue.async {
            let result = Result { try service.capture(applicationID: id, name: name, sources: sources, reason: "用户手动保留恢复资料", progress: { copied, total in
                DispatchQueue.main.async { self.message.stringValue = "正在核对文件：\(copied) / \(total)" }
            }) }
            DispatchQueue.main.async {
                self.busy = false
                switch result {
                case .success(let snapshot): self.message.stringValue = snapshot.manifest.stage; self.notify(snapshot.manifest.stage); self.refresh()
                case .failure(let error): self.message.stringValue = error.localizedDescription; self.updateButtons()
                }
            }
        }
    }
    @objc func revealSnapshot() {
        if let selected { NSWorkspace.shared.activateFileViewerSelecting([selected.directory]) }
    }
    @objc func recordOutput() {
        guard let selected, !busy else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.canChooseFiles = true
        panel.prompt = "记录另存文件"; panel.message = "先在原应用中另存并等待保存完成，再选择新文件。此操作仅记录校验信息，不修改文件。"
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let file = panel.url else { return }
            self.perform { service in try service.recordOutput(file, snapshot: selected) }
        }
    }
    @objc func confirmOutput() {
        guard let selected, !busy else { return }
        let alert = NSAlert(); alert.messageText = "确认新文件包含需要找回的修改？"
        alert.informativeText = "请先重新打开另存文件，检查内容。此确认由您作出，不根据文件名、大小或恢复提示自动判断。"
        alert.addButton(withTitle: "内容已确认"); alert.addButton(withTitle: "尚未确认")
        alert.buttons[0].keyEquivalent = ""
        alert.beginSheetModal(for: window) { response in
            if response == .alertFirstButtonReturn { self.perform { try $0.confirmContent(selected) } }
        }
        alert.window.defaultButtonCell = nil
    }
    func perform(_ operation: @escaping (RecoveryService) throws -> RecoverySnapshot) {
        busy = true; updateButtons(); let service = serviceProvider()
        queue.async {
            let result = Result { try operation(service) }
            DispatchQueue.main.async {
                self.busy = false
                switch result {
                case .success(let snapshot): self.notify(snapshot.manifest.stage); self.refresh()
                case .failure(let error): self.message.stringValue = error.localizedDescription; self.updateButtons()
                }
            }
        }
    }
    @objc func showGuide() {
        let alert = NSAlert(); alert.messageText = "崩溃后的处理顺序"
        alert.informativeText = "1. 先检查并保留完整恢复目录；也可使用「保留文件或目录」备份原设计文件。避免反复重启或清理缓存。\n2. 打开 Illustrator 或 Photoshop，使用原应用自身恢复，确认实际打开了文档。\n3. 另存为新的文件，保留原文件，等待保存过程结束。\n4. 在这里记录另存文件；重新打开核对内容后，确认恢复结果。\n\n.aishm 是恢复机制中的数据，不能简单改名为 .ai。快照不能恢复已经被删除且不存在的数据；本工具不扫描磁盘扇区，也不回灌恢复目录。\n\n恢复目录仍在写入时，一次快照可能不完整。可保留第二份快照并比较记录；原始资料始终保留。"
        alert.addButton(withTitle: "关闭"); alert.beginSheetModal(for: window)
    }
}
