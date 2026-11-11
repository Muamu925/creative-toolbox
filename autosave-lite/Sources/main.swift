import AppKit
import ServiceManagement
import Darwin

final class ApplicationToggle: NSButton { var applicationID = "" }

final class SaveApp: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let policy = SavePolicy()
    let backend = MacSaveBackend()
    let registry = SessionRegistry()
    let recoveryQueue = DispatchQueue(label: "org.creativetoolbox.autosave.rescue", qos: .utility)
    var recoveryWindow: RecoveryWindow?
    let rescueButton = NSButton(title: "崩溃抢救…", target: nil, action: nil)
    let menuRescue = NSMenuItem(title: "崩溃抢救…", action: #selector(showRecovery), keyEquivalent: "")
    var rescueMessage: String?

    let gate = DispatchGate()
    let queue = DispatchQueue(label: "org.creativetoolbox.autosave.observe", qos: .utility)
    var settings = SaveSettings()
    var store: SettingsStore!
    var root: URL!
    var statusItem: NSStatusItem!
    var window: NSWindow!
    var timer: Timer?
    var timerInterval = 0.0
    var observers: [NSObjectProtocol] = []
    var sleepObservers: [NSObjectProtocol] = []
    var picker: ApplicationPicker?
    var prompt: NSAlert?
    var prompting: ApplicationSession?
    var promptWasVisible = false
    var workInFlight = false
    var suspended = false
    var settingsError: String?
    var loginError: String?
    var lastRequest = "本次尚未发送保存请求"
    var requests = 0
    var lockFD: Int32 = -1
    var smokeDirectory: URL?
    var lastReconcile = -Double.infinity
    var lastPermissions = SavePermissions.current()
    var displayedApplications = ""
    var displayedStatus = ""
    var decision = SaveDecision(code: "waiting", message: "等待所选应用启动。")
    let stateLabel = NSTextField(labelWithString: "")
    let detailLabel = NSTextField(wrappingLabelWithString: "")
    let lastLabel = NSTextField(wrappingLabelWithString: "")
    let permissionLabel = NSTextField(wrappingLabelWithString: "")
    let permissionTitle = NSTextField(labelWithString: "系统权限")
    let loginLabel = NSTextField(wrappingLabelWithString: "")
    let applications = NSStackView()
    let intervalPopup = NSPopUpButton()
    let idlePopup = NSPopUpButton()
    let statusGlyph = NSImageView()
    let loginToggle = NSButton(checkboxWithTitle: "登录 Mac 后自动启动", target: nil, action: nil)
    let pauseButton = NSButton(title: "暂停检测", target: nil, action: nil)
    let menuState = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    let menuLast = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    let menuPause = NSMenuItem(title: "暂停检测", action: #selector(toggleDetection), keyEquivalent: "")
    let menuSessions = NSMenuItem(title: "本次应用状态", action: nil, keyEquivalent: "")
    let formatter: DateFormatter = { let f = DateFormatter(); f.dateFormat = "HH:mm:ss"; return f }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--inspect-frontmost"), args.indices.contains(i + 1) {
            inspectFrontmost(to: URL(fileURLWithPath: args[i + 1])); return
        }
        if let i = args.firstIndex(of: "--smoke-dir"), args.indices.contains(i + 1) {
            smokeDirectory = URL(fileURLWithPath: args[i + 1], isDirectory: true)
        }
        root = smokeDirectory ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AutosaveLite", isDirectory: true)
        do { try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true) }
        catch { fatalStartup("无法创建设置目录：\(error.localizedDescription)"); return }
        if smokeDirectory == nil {
            lockFD = open(root.appendingPathComponent("instance.lock").path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
            guard lockFD >= 0, flock(lockFD, LOCK_EX | LOCK_NB) == 0 else {
                NSRunningApplication.runningApplications(withBundleIdentifier: Product.bundleID)
                    .first(where: { $0.processIdentifier != getpid() })?.activate(options: [.activateIgnoringOtherApps])
                NSApp.terminate(nil); return
            }
        }
        store = SettingsStore(url: root.appendingPathComponent("settings.json"))
        let firstLaunch = !FileManager.default.fileExists(atPath: store.url.path)
        if smokeDirectory != nil { settings.enabled = false }
        else {
            settings = store.load()
            if firstLaunch {
                settings.applications = settings.applications.filter { NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0) != nil }
                _ = persist(settings)
            }
        }
        if let warning = store.warning { settingsError = warning }
        buildMenu(); buildWindow()
        let center = NSWorkspace.shared.notificationCenter
        for name in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                self?.gate.invalidate(); self?.reconcile(); self?.tick()
            })
        }
        observers.append(center.addObserver(forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main) { [weak self] _ in
            self?.gate.invalidate(); self?.policy.invalidateForeground(); self?.tick()
        })
        for name in [NSWorkspace.willSleepNotification, NSWorkspace.sessionDidResignActiveNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.setSuspended(true) })
        }
        for name in [NSWorkspace.didWakeNotification, NSWorkspace.sessionDidBecomeActiveNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.setSuspended(false) })
        }
        let distributed = DistributedNotificationCenter.default()
        for (name, value) in [("com.apple.screenIsLocked", true), ("com.apple.screenIsUnlocked", false)] {
            sleepObservers.append(distributed.addObserver(forName: Notification.Name(name), object: nil, queue: .main) { [weak self] _ in self?.setSuspended(value) })
        }
        reconcile()
        refreshLogin()
        if firstLaunch || smokeDirectory != nil || settingsError != nil { showWindow() }
        tick()
        if let dir = smokeDirectory {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.smoke(dir) }
        }
    }
    func fatalStartup(_ message: String) {
        let alert = NSAlert(); alert.messageText = "自动保存无法启动"; alert.informativeText = message
        alert.runModal(); NSApp.terminate(nil)
    }
    // Read-only acceptance probe: never creates a save request or loads settings.
    func inspectFrontmost(to destination: URL) {
        let permissions = SavePermissions.current()
        var report: [String: Any] = ["read_only": true, "requests_sent": 0,
            "permissions": ["accessibility": permissions.accessibility, "input_monitoring": permissions.listening, "posting": permissions.posting]]
        if let front = NSWorkspace.shared.frontmostApplication.flatMap(ApplicationDiscovery.session) {
            let state = backend.observe(session: front, permissions: permissions)
            report["application_id"] = front.id; report["application_name"] = front.name
            report["document_identified"] = state.target?.document.isEmpty == false
            report["blocked_reason"] = state.blocked ?? (permissions.ready ? "" : "系统权限不足")
            report["idle_seconds"] = state.idle; report["pressed"] = state.pressed
            if let edited = state.edited { report["edited"] = edited }
        }
        report["protected_observations"] = backend.protectedObservations
        do {
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: destination)
        } catch { fputs("Read-only inspection failed: \(error)\n", stderr); exit(1) }
        NSApp.terminate(nil)
    }
    func label(_ text: String, size: CGFloat = 13, secondary: Bool = false) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.font = .systemFont(ofSize: size); field.textColor = secondary ? .secondaryLabelColor : .labelColor
        return field
    }
    func button(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action); b.bezelStyle = .rounded; return b
    }
    func row(_ views: [NSView]) -> NSStackView {
        let row = NSStackView(); row.spacing = 10; row.alignment = .centerY; row.detachesHiddenViews = false
        for view in views { row.addArrangedSubview(view); row.setVisibilityPriority(.mustHold, for: view) }
        return row
    }
    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 500, height: 680),
                          styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "Autosave Lite"; window.minSize = NSSize(width: 460, height: 700)
        window.isReleasedWhenClosed = false; window.delegate = self; window.center()
        window.contentView = PanelBackground(frame: window.contentView!.bounds)
        let root = NativeStyle.column([], spacing: 10)
        root.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 22),
            root.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -22),
            root.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 18),
            root.bottomAnchor.constraint(lessThanOrEqualTo: window.contentView!.bottomAnchor, constant: -16)
        ])
        let heading = label("Autosave Lite", size: 22); heading.font = .systemFont(ofSize: 22, weight: .semibold)
        let brand = NativeStyle.column([heading, label("自动保存与崩溃抢救", size: 11, secondary: true)], spacing: 3)
        pauseButton.bezelStyle = .rounded; pauseButton.controlSize = .regular
        pauseButton.target = self; pauseButton.action = #selector(toggleDetection)
        let header = row([NativeStyle.symbol("command.square.fill", size: 34, color: .controlAccentColor),
                          brand, NSView(), pauseButton])
        root.addArrangedSubview(header)

        stateLabel.font = .systemFont(ofSize: 15, weight: .semibold)
        statusGlyph.image = NSImage(systemSymbolName: "clock", accessibilityDescription: nil)
        statusGlyph.widthAnchor.constraint(equalToConstant: 19).isActive = true
        statusGlyph.heightAnchor.constraint(equalToConstant: 19).isActive = true
        let statusRow = row([statusGlyph, stateLabel, NSView()])
        detailLabel.font = .systemFont(ofSize: 12); detailLabel.textColor = .secondaryLabelColor
        detailLabel.maximumNumberOfLines = 3
        detailLabel.heightAnchor.constraint(greaterThanOrEqualToConstant: 30).isActive = true
        lastLabel.font = .monospacedDigitSystemFont(ofSize: 11, weight: .regular); lastLabel.textColor = .secondaryLabelColor
        let statusLine = NativeStyle.separator()
        let statusContents = NativeStyle.column([statusRow, detailLabel, statusLine, lastLabel], spacing: 8)
        for v in [statusRow, detailLabel, statusLine, lastLabel] { v.widthAnchor.constraint(equalTo: statusContents.widthAnchor).isActive = true }
        let statusCard = NativeStyle.card(statusContents); root.addArrangedSubview(statusCard)

        let appsTitle = label("应用", size: 13); appsTitle.font = .systemFont(ofSize: 13, weight: .semibold)
        let addButton = button("添加应用…", #selector(addApplication)); addButton.controlSize = .small
        let appsHeader = row([appsTitle, NSView(), addButton]); root.addArrangedSubview(appsHeader)
        applications.orientation = .vertical; applications.alignment = .leading; applications.spacing = 0
        applications.edgeInsets = NSEdgeInsets(top: 3, left: 2, bottom: 3, right: 2)
        applications.translatesAutoresizingMaskIntoConstraints = false
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.drawsBackground = false
        let container = FlippedView(); container.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(applications); scroll.documentView = container
        NSLayoutConstraint.activate([
            applications.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            applications.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            applications.topAnchor.constraint(equalTo: container.topAnchor),
            applications.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            container.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor)
        ])
        scroll.heightAnchor.constraint(equalToConstant: 96).isActive = true
        let appsContents = NativeStyle.column([scroll]); scroll.widthAnchor.constraint(equalTo: appsContents.widthAnchor).isActive = true
        let appsCard = NativeStyle.card(appsContents, inset: 8); root.addArrangedSubview(appsCard)

        for seconds in SaveSettings.intervals {
            intervalPopup.addItem(withTitle: seconds < 60 ? "\(seconds) 秒" : "\(seconds / 60) 分钟")
            intervalPopup.lastItem?.tag = seconds
        }
        intervalPopup.selectItem(withTag: settings.interval); intervalPopup.controlSize = .small
        intervalPopup.target = self; intervalPopup.action = #selector(changeInterval)
        for seconds in SaveSettings.idleOptions { idlePopup.addItem(withTitle: "\(seconds) 秒"); idlePopup.lastItem?.tag = seconds }
        idlePopup.selectItem(withTag: settings.idleSeconds); idlePopup.controlSize = .small
        idlePopup.target = self; idlePopup.action = #selector(changeIdle)
        let timingTitle = label("保存时机", size: 13); timingTitle.font = .systemFont(ofSize: 13, weight: .semibold)
        let intervalRow = row([label("最短间隔", size: 12), intervalPopup, NSView(), label("连续空闲", size: 12), idlePopup])

        let timingHint = label("达到间隔后等待空闲；没有新操作时不重复发送。", size: 11, secondary: true)
        let timingLine = NativeStyle.separator()
        loginToggle.target = self; loginToggle.action = #selector(changeLogin); loginToggle.font = .systemFont(ofSize: 12)
        loginLabel.font = .systemFont(ofSize: 10); loginLabel.textColor = .secondaryLabelColor
        let loginSettings = button("系统设置…", #selector(openLoginSettings)); loginSettings.controlSize = .small
        let loginRow = row([loginToggle, NSView(), loginSettings])
        let timingContents = NativeStyle.column([timingTitle, intervalRow, timingHint, timingLine, loginRow, loginLabel], spacing: 8)
        for v in [intervalRow, timingHint, timingLine, loginRow, loginLabel] {
            v.widthAnchor.constraint(equalTo: timingContents.widthAnchor).isActive = true
        }
        let timingCard = NativeStyle.card(timingContents); root.addArrangedSubview(timingCard)

        permissionTitle.font = .systemFont(ofSize: 13, weight: .semibold)
        permissionLabel.font = .systemFont(ofSize: 11); permissionLabel.textColor = .secondaryLabelColor
        let access = button("辅助功能…", #selector(openAccessibility))
        let input = button("输入监控…", #selector(openInputMonitoring))
        let posting = button("事件发送…", #selector(openEventPosting))
        let check = button("重新检查", #selector(recheckPermissions))
        for b in [access, input, posting, check] { b.controlSize = .small }
        let permissionButtons = row([access, input, posting, NSView(), check])
        let permissionContents = NativeStyle.column([permissionTitle, permissionLabel, permissionButtons], spacing: 8)
        for v in [permissionLabel, permissionButtons] { v.widthAnchor.constraint(equalTo: permissionContents.widthAnchor).isActive = true }
        let permissionCard = NativeStyle.card(permissionContents); root.addArrangedSubview(permissionCard)
        let note = label("仅处理已保存过的前台文档。", size: 10, secondary: true)
        let help = button("保存规则", #selector(showRules)); help.controlSize = .small
        rescueButton.bezelStyle = .rounded; rescueButton.controlSize = .small
        rescueButton.target = self; rescueButton.action = #selector(showRecovery)
        let footer = row([note, NSView(), rescueButton, help]); root.addArrangedSubview(footer)
        for v in [header, statusCard, appsHeader, appsCard, timingCard, permissionCard, footer] {
            v.widthAnchor.constraint(equalTo: root.widthAnchor).isActive = true
        }
    }
    func buildMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu(); menu.autoenablesItems = false
        menuState.isEnabled = false; menuLast.isEnabled = false
        menu.addItem(menuState); menu.addItem(menuLast); menu.addItem(menuSessions)
        menuRescue.target = self; menu.addItem(menuRescue); menu.addItem(.separator())
        for (title, action, key) in [("打开 Autosave Lite…", #selector(showWindow), ","), ("登录项设置…", #selector(openLoginSettings), "")] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key); item.target = self; menu.addItem(item)
        }
        menuPause.target = self; menu.addItem(menuPause); menu.addItem(.separator())
        let quitItem = NSMenuItem(title: "退出 Autosave Lite", action: #selector(quit), keyEquivalent: "q"); quitItem.target = self; menu.addItem(quitItem)
        statusItem.menu = menu
        let main = NSMenu(); let application = NSMenuItem(); let appMenu = NSMenu()
        let settingsItem = NSMenuItem(title: "设置…", action: #selector(showWindow), keyEquivalent: ",")
        settingsItem.target = self; appMenu.addItem(settingsItem)
        let q = NSMenuItem(title: "退出 Autosave Lite", action: #selector(quit), keyEquivalent: "q"); q.target = self; appMenu.addItem(q)
        application.submenu = appMenu; main.addItem(application); NSApp.mainMenu = main
    }
    func persist(_ candidate: SaveSettings) -> Bool {
        do { try store.save(candidate); settings = candidate; settingsError = nil; gate.invalidate(); return true }
        catch { settingsError = "设置未能保存：\(error.localizedDescription)"; return false }
    }
    func name(_ id: String) -> String { settings.customNames[id] ?? DesignApp.name(id) }
    func sessionText(_ session: ApplicationSession) -> String {
        switch registry.choices[session.key] {
        case .approved: return settings.enabled ? (lastPermissions.ready ? "本次已启用" : "本次已同意，待授权") : "本次已同意，检测暂停"
        case .declined: return "本次未启用"
        default: return "等待本次确认"
        }
    }
    func renderApplications() {
        let ids = Array(Set(settings.applications + Array(settings.customNames.keys))).sorted { name($0) < name($1) }
        let fingerprint = ids.map { id in
            id + String(settings.applications.contains(id)) + registry.sessions.values.filter { $0.id == id }
                .sorted { $0.key < $1.key }.map { $0.key + sessionText($0) }.joined()
        }.joined() + String(settings.enabled) + String(lastPermissions.ready)
        guard fingerprint != displayedApplications else { return }
        displayedApplications = fingerprint
        for view in applications.arrangedSubviews { applications.removeArrangedSubview(view); view.removeFromSuperview() }
        if ids.isEmpty { applications.addArrangedSubview(label("尚未选择应用，请添加需要自动保存的软件。", secondary: true)) }
        for id in ids {
            let toggle = ApplicationToggle(checkboxWithTitle: "", target: self, action: #selector(toggleApplication(_:)))
            toggle.applicationID = id; toggle.state = settings.applications.contains(id) ? .on : .off
            let sessions = registry.sessions.values.filter { $0.id == id }.sorted { $0.key < $1.key }
            let installed = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id) != nil
                || settings.applicationPaths[id].map { FileManager.default.fileExists(atPath: $0) } == true
            let state = !settings.applications.contains(id) ? "未选择" : sessions.isEmpty
                ? (installed ? "等待应用启动 · 兼容性待验证" : "未检测到安装位置")
                : sessions.map { sessionText($0) }.joined(separator: "；")
            let subtitle = label(state, size: 10, secondary: true)
            let appTitle = label(name(id), size: 12); appTitle.font = .systemFont(ofSize: 12, weight: .medium)
            let lines = NativeStyle.column([appTitle, subtitle], spacing: 3)
            let icon = NSImageView()
            let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id)
                ?? settings.applicationPaths[id].map { URL(fileURLWithPath: $0) }
            icon.image = url.map { NSWorkspace.shared.icon(forFile: $0.path) }
                ?? NSImage(systemSymbolName: "app", accessibilityDescription: nil)
            icon.widthAnchor.constraint(equalToConstant: 28).isActive = true
            icon.heightAnchor.constraint(equalToConstant: 28).isActive = true
            let entry = row([icon, lines, NSView(), toggle])
            entry.edgeInsets = NSEdgeInsets(top: 8, left: 6, bottom: 8, right: 6)
            toggle.setAccessibilityLabel("选择 \(name(id))")
            applications.addArrangedSubview(entry)
            entry.widthAnchor.constraint(equalTo: applications.widthAnchor).isActive = true
        }
        let sessionsMenu = NSMenu(); sessionsMenu.autoenablesItems = false
        for session in registry.sessions.values.sorted(by: { $0.name < $1.name }) {
            let sub = NSMenuItem(title: "\(session.name) · \(sessionText(session))", action: nil, keyEquivalent: "")
            let actions = NSMenu()
            for (title, selector) in [("重新确认本次保护…", #selector(confirmAgain(_:))), ("结束本次保护", #selector(endSession(_:)))] {
                let item = NSMenuItem(title: title, action: selector, keyEquivalent: ""); item.target = self; item.representedObject = session.key
                actions.addItem(item)
            }
            sub.submenu = actions; sessionsMenu.addItem(sub)
        }
        menuSessions.submenu = sessionsMenu; menuSessions.isEnabled = !registry.sessions.isEmpty
    }
    @objc func confirmAgain(_ sender: NSMenuItem) {
        guard let key = sender.representedObject as? String, let session = registry.sessions[key] else { return }
        registry.requestAgain(session); policy.ended(processKey: key); gate.invalidate(); tick()
    }
    @objc func endSession(_ sender: NSMenuItem) {
        guard let key = sender.representedObject as? String, let session = registry.sessions[key] else { return }
        registry.decide(session, approved: false); policy.ended(processKey: key); gate.invalidate(); tick()
    }
    @objc func toggleApplication(_ sender: ApplicationToggle) {
        var candidate = settings
        if sender.state == .on {
            if !candidate.applications.contains(sender.applicationID) { candidate.applications.append(sender.applicationID) }
        } else { candidate.applications.removeAll { $0 == sender.applicationID } }
        _ = persist(candidate); displayedApplications = ""; reconcile(); tick()
    }
    @objc func addApplication() {
        guard window.attachedSheet == nil else { return }
        picker = ApplicationPicker(selected: Set(settings.applications)) { [weak self] app in
            guard let self else { return false }
            var candidate = self.settings
            if !candidate.applications.contains(app.id) { candidate.applications.append(app.id) }
            candidate.customNames[app.id] = app.name; candidate.applicationPaths[app.id] = app.path
            let saved = self.persist(candidate); self.reconcile(); self.tick(); return saved
        }
        picker?.begin(for: window)
    }
    @objc func changeInterval() {
        var candidate = settings; candidate.interval = intervalPopup.selectedTag()
        _ = persist(candidate); intervalPopup.selectItem(withTag: settings.interval); tick()
    }
    @objc func changeIdle() {
        var candidate = settings; candidate.idleSeconds = idlePopup.selectedTag()
        if persist(candidate) { policy.invalidateForeground() }
        idlePopup.selectItem(withTag: settings.idleSeconds); tick()
    }
    @objc func showRules() {
        guard window.attachedSheet == nil else { return }
        let alert = NSAlert()
        alert.messageText = "自动保存规则"
        alert.informativeText = "每次启动目标应用时，需要确认是否启用本次保护。\n\n最短间隔达到 \(settings.interval) 秒后，等待连续 \(settings.idleSeconds) 秒无键鼠操作、所有按键及鼠标按钮松开，并确认前台文档未切换，再发送一次 ⌘S。\n\n移动鼠标会延后请求，但不单独产生新的待保存操作。没有新操作时不会周期性重复发送。\n\n新文档请先手动保存。已发送 ⌘S 仅表示请求已提交，不表示应用已完成文件写入。"
        alert.addButton(withTitle: "关闭")
        alert.beginSheetModal(for: window)
    }
    @objc func toggleDetection() {
        var candidate = settings; candidate.enabled.toggle()
        if persist(candidate) { policy.reset() }
        if !settings.enabled, let alert = prompt { window.endSheet(alert.window, returnCode: .abort) }
        tick()
    }
    func reconcile() {
        let live = ApplicationDiscovery.running().compactMap(\.session)
        let previous = registry.sessions
        let ended = registry.reconcile(running: live, selected: Set(settings.applications))
        if !ended.isEmpty {
            gate.invalidate()
            for key in ended {
                policy.ended(processKey: key)
                if let session = previous[key], !live.contains(where: { $0.key == key }) { preserveAfterExit(session) }
            }
        }
        if let session = prompting, registry.sessions[session.key] == nil, let alert = prompt {
            window.endSheet(alert.window, returnCode: .abort)
        }
        lastReconcile = ProcessInfo.processInfo.systemUptime
    }
    func recoveryService() -> RecoveryService {
        let location = settings.rescueDirectory.map { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? root.appendingPathComponent("Rescue", isDirectory: true)
        return RecoveryService(storage: location)
    }
    func recoveryStatus(_ message: String) {
        rescueMessage = message
        menuRescue.title = "崩溃抢救 · \(message)"
        rescueButton.title = "查看抢救记录…"
    }
    @objc func showRecovery() {
        if recoveryWindow == nil {
            recoveryWindow = RecoveryWindow(queue: recoveryQueue, service: { [unowned self] in self.recoveryService() },
                changeSettings: { [weak self] enabled, path in
                    guard let self else { return }
                    var candidate = self.settings
                    if let enabled { candidate.rescueEnabled = enabled }
                    if let path { candidate.rescueDirectory = path }
                    _ = self.persist(candidate)
                    self.recoveryWindow?.automatic.state = self.settings.rescueEnabled ? .on : .off
                    self.render()
                }, notify: { [weak self] message in self?.recoveryStatus(message) })
        }
        recoveryWindow?.show(enabled: settings.rescueEnabled)
    }
    func preserveAfterExit(_ session: ApplicationSession) {
        guard smokeDirectory == nil, settings.enabled, settings.rescueEnabled,
              RecoveryDiscovery.supported.contains(where: { $0.id == session.id }) else { return }
        let service = recoveryService()
        recoveryQueue.async {
            let sources = RecoveryDiscovery.sources(for: session.id)
            guard !sources.isEmpty else { return }
            do {
                let snapshot = try service.capture(applicationID: session.id, name: session.name, sources: sources,
                    reason: "所选应用已退出并遗留恢复数据；退出原因尚未确认，不能直接判断为崩溃。")
                DispatchQueue.main.async {
                    self.recoveryStatus("\(session.name) · \(snapshot.manifest.stage)")
                    if self.recoveryWindow?.window.isVisible == true { self.recoveryWindow?.refresh() }
                }
            } catch RecoveryFailure.noData {
                // A normal exit commonly removes recovery data. No success claim.
            } catch {
                DispatchQueue.main.async { self.recoveryStatus("快照未完成：\(error.localizedDescription)") }
            }
        }
    }
    func setSuspended(_ value: Bool) {
        suspended = value; gate.invalidate(); policy.reset()
        if value, let alert = prompt { window.endSheet(alert.window, returnCode: .abort) }
        if !value { reconcile() }
        tick()
    }
    func scheduleTimer(_ interval: Double) {
        guard timerInterval != interval else { return }
        timer?.invalidate(); timerInterval = interval
        let t = Timer(timeInterval: interval, target: self, selector: #selector(tick), userInfo: nil, repeats: true)
        t.tolerance = interval == 1 ? 0.15 : 1
        RunLoop.main.add(t, forMode: .common); timer = t
    }
    func refreshPermissions() {
        let permissions = SavePermissions.current()
        if permissions != lastPermissions {
            lastPermissions = permissions
            gate.invalidate(); policy.invalidateForeground()
        }
        if permissions.ready && decision.code == "permission" {
            decision = SaveDecision(code: "waiting", message: "权限已就绪，等待保存条件满足。")
        }
    }
    @objc func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        if now - lastReconcile >= 15 { reconcile(); refreshLogin() }
        refreshPermissions()
        let permissions = lastPermissions
        let front = NSWorkspace.shared.frontmostApplication.flatMap(ApplicationDiscovery.session)
        let eligible = settings.enabled && !suspended && smokeDirectory == nil && prompt == nil
            && front.map { registry.approvedKeys.contains($0.key) } == true
        scheduleTimer(eligible && permissions.ready ? 1 : 5)
        if !settings.enabled { decision = SaveDecision(code: "paused", message: "检测已暂停，不会发送保存请求。") }
        else if suspended { decision = SaveDecision(code: "suspended", message: "等待返回活动桌面。") }
        else if !permissions.ready && registry.approvedCount > 0 { decision = SaveDecision(code: "permission", message: "本次已同意，自动保存待授权。") }
        else if !eligible {
            policy.invalidateForeground()
            decision = SaveDecision(code: "waiting", message: registry.nextPending != nil ? "等待确认是否启用本次保护。" : "等待已确认的应用和文档位于前台。")
        }
        render()
        if smokeDirectory == nil && settings.enabled && !suspended && prompt == nil && window.attachedSheet == nil,
           let pending = registry.nextPending { askAbout(pending); return }
        guard eligible, permissions.ready, let session = front, !workInFlight else { return }
        workInFlight = true
        let ticket = gate.ticket()
        queue.async {
            let observation = self.backend.observe(session: session, permissions: permissions)
            DispatchQueue.main.async {
                guard self.gate.valid(ticket) else { self.workInFlight = false; return }
                self.decision = self.policy.evaluate(observation, settings: self.settings,
                    now: ProcessInfo.processInfo.systemUptime, ownPID: getpid(), approved: self.registry.approvedKeys)
                self.render()
                guard self.decision.due else { self.workInFlight = false; return }
                let requiredIdle = self.settings.idleSeconds
                self.queue.async {
                    let result = self.backend.sendSave(expected: observation, idleRequired: Double(requiredIdle), stillAuthorized: { self.gate.valid(ticket) })
                    DispatchQueue.main.async {
                        self.workInFlight = false
                        switch result {
                        case .sent:
                            if self.gate.valid(ticket) { self.policy.sent(observation, now: ProcessInfo.processInfo.systemUptime) }
                            self.requests += 1
                            self.lastRequest = "\(self.formatter.string(from: Date())) · 已向 \(session.name) 发送 ⌘S"
                            self.decision = SaveDecision(code: "sent", message: "保存请求已提交，等待后续操作。")
                        case .cancelled:
                            if self.gate.valid(ticket) { self.policy.cancelled(processKey: session.key, now: ProcessInfo.processInfo.systemUptime) }
                            self.decision = SaveDecision(code: "cancelled", message: "前台或输入状态已变化，保存请求已取消。")
                        case .unavailable(let reason):
                            self.policy.cancelled(processKey: session.key, now: ProcessInfo.processInfo.systemUptime)
                            self.decision = SaveDecision(code: "unavailable", message: reason)
                        }
                        self.render()
                    }
                }
            }
        }
    }
    func render() {
        let title: String
        if !settings.enabled { title = "检测已暂停" }
        else if suspended { title = "等待返回桌面" }
        else if !lastPermissions.ready && registry.approvedCount > 0 { title = "自动保存待授权" }
        else if registry.nextPending != nil { title = "等待本次确认" }
        else if registry.approvedCount == 0 { title = registry.sessions.isEmpty ? "等待应用启动" : "本次未启用" }
        else if decision.code == "blocked" || decision.code == "unavailable" { title = "等待保存条件" }
        else { title = "本次保护已启用" }
        let detail = settingsError ?? loginError ?? (title == "自动保存待授权" ? "本次已同意，自动保存待授权。" : decision.message)
        let fingerprint = [title, detail, lastRequest, lastPermissions.description, String(settings.enabled)].joined(separator: "|")
        renderApplications()
        guard fingerprint != displayedStatus else { return }
        displayedStatus = fingerprint
        statusGlyph.image = NSImage(systemSymbolName: !settings.enabled ? "pause.circle" :
            title == "自动保存待授权" ? "exclamationmark.circle" :
            title == "本次保护已启用" ? "checkmark.circle" : "clock", accessibilityDescription: title)
        statusGlyph.contentTintColor = title == "自动保存待授权" ? .systemOrange : .controlAccentColor
        stateLabel.stringValue = title
        stateLabel.textColor = title == "本次保护已启用" ? .labelColor : .secondaryLabelColor
        detailLabel.stringValue = detail
        lastLabel.stringValue = lastRequest
        permissionLabel.stringValue = "\(lastPermissions.description)\n\(lastPermissions.guidance)"
        pauseButton.title = settings.enabled ? "暂停检测" : "继续检测"; menuPause.title = settings.enabled ? "暂停检测" : "继续检测"
        menuState.title = title; menuLast.title = lastRequest
        statusItem.button?.image = NSImage(systemSymbolName: !settings.enabled ? "pause.circle" :
            !lastPermissions.ready && registry.approvedCount > 0 ? "exclamationmark.circle" : "command.circle",
            accessibilityDescription: title)
        statusItem.button?.toolTip = "自动保存 · \(title)\n\(detailLabel.stringValue)"
    }
    func askAbout(_ session: ApplicationSession) {
        gate.invalidate(); policy.invalidateForeground()
        let alert = NSAlert()
        alert.messageText = "是否为本次 \(session.name) 会话启用自动保存？"
        alert.informativeText = "启用后，在保存间隔达到 \(settings.interval) 秒且停止操作 \(settings.idleSeconds) 秒后，向前台文档发送 ⌘S。应用退出后，本次保护结束。\n\n新文档请先手动保存，确定文件名称和位置。"
        alert.addButton(withTitle: "启用本次保护")
        alert.addButton(withTitle: "本次不启用")
        // Return/Escape must never accidentally approve a just-appeared prompt.
        alert.buttons[0].keyEquivalent = ""; alert.buttons[1].keyEquivalent = "\u{1b}"
        prompting = session; prompt = alert; promptWasVisible = window.isVisible
        showWindow()
        alert.beginSheetModal(for: window) { [weak self] response in
            guard let self else { return }
            self.prompt = nil; self.prompting = nil
            self.reconcile()
            // A suspension abort leaves the question pending for the next unlock.
            if !self.suspended && self.settings.enabled {
                self.registry.decide(session, approved: response == .alertFirstButtonReturn)
            }
            self.gate.invalidate()
            if !self.promptWasVisible { self.window.orderOut(nil) }
            self.tick()
        }
        alert.window.defaultButtonCell = nil
    }
    @objc func openAccessibility() {
        if !SavePermissions.current().accessibility { SavePermissions.requestAccessibility() }
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
    }
    @objc func openInputMonitoring() {
        if !SavePermissions.current().listening { SavePermissions.requestInputMonitoring() }
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent")!)
    }
    @objc func openEventPosting() {
        if !SavePermissions.current().posting { SavePermissions.requestEventPosting() }
        recheckPermissions()
    }
    @objc func recheckPermissions() {
        gate.invalidate()
        refreshPermissions()
        permissionTitle.stringValue = "系统权限 · 已检查 \(formatter.string(from: Date()))"
        render()
    }
    @objc func openLoginSettings() { SMAppService.openSystemSettingsLoginItems() }
    @objc func changeLogin() { setLogin(loginToggle.state != .off) }
    func setLogin(_ enabled: Bool) {
        guard smokeDirectory == nil else { return }
        guard Bundle.main.bundleURL.path.hasPrefix("/Applications/") else {
            loginError = "请先将应用移入“应用程序”，再启用登录启动。"; refreshLogin(); render(); return
        }
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            loginError = nil
        } catch { loginError = "登录启动未能设置：\(error.localizedDescription)" }
        refreshLogin(); render()
    }
    func refreshLogin() {
        guard window != nil else { return }
        if smokeDirectory != nil { loginToggle.state = .off; loginLabel.stringValue = "测试运行：未修改登录项"; return }
        switch SMAppService.mainApp.status {
        case .enabled: loginToggle.state = .on; loginLabel.stringValue = "登录启动已启用"
        case .requiresApproval: loginToggle.state = .mixed; loginLabel.stringValue = "登录启动待系统批准，可从菜单打开登录项设置。"
        case .notFound: loginToggle.state = .off; loginLabel.stringValue = "系统未找到登录项，请从安装位置重新设置。"
        default: loginToggle.state = .off; loginLabel.stringValue = "登录启动未启用"
        }
    }
    @objc func showWindow() {
        refreshLogin(); refreshPermissions(); render()
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    @objc func quit() { gate.invalidate(); timer?.invalidate(); NSApp.terminate(nil) }
    func applicationWillTerminate(_ notification: Notification) {
        gate.invalidate()
        if lockFD >= 0 { flock(lockFD, LOCK_UN); Darwin.close(lockFD) }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationDidBecomeActive(_ notification: Notification) {
        guard window != nil else { return }
        refreshLogin(); refreshPermissions(); render()
    }

    func capture(_ view: NSView, to url: URL) throws {
        view.layoutSubtreeIfNeeded()
        guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { throw CocoaError(.fileWriteUnknown) }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        guard let data = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try data.write(to: url)
    }
    func smoke(_ directory: URL) {
        do {
            recheckPermissions()
            try capture(window.contentView!, to: directory.appendingPathComponent("settings-500.png"))
            window.setContentSize(NSSize(width: 460, height: 680))
            try capture(window.contentView!, to: directory.appendingPathComponent("settings-460.png"))
            window.appearance = NSAppearance(named: .darkAqua)
            try capture(window.contentView!, to: directory.appendingPathComponent("settings-dark.png"))
            window.appearance = nil
            showRecovery()
            try capture(recoveryWindow!.window.contentView!, to: directory.appendingPathComponent("rescue-center.png"))
            recoveryWindow?.window.orderOut(nil)
            let running = ApplicationDiscovery.running()
            let picker = ApplicationPicker(selected: Set(settings.applications)) { _ in false }
            picker.panel.orderFront(nil)
            try capture(picker.panel.contentView!, to: directory.appendingPathComponent("running-applications.png"))
            let query = running.first?.name ?? "不存在的应用"
            picker.search.stringValue = query; picker.applySearch()
            let searchPassed = picker.filtered.allSatisfy { $0.name.localizedCaseInsensitiveContains(query) || $0.id.localizedCaseInsensitiveContains(query) }
            picker.close()
            let settingsCopy = SettingsStore(url: directory.appendingPathComponent("smoke-settings.json"))
            var candidate = settings
            for app in ApplicationDiscovery.candidates(running).prefix(2) {
                if !candidate.applications.contains(app.id) { candidate.applications.append(app.id) }
            }
            try settingsCopy.save(candidate)
            let recheckDisplayed = permissionTitle.stringValue.contains("已检查")
            guard settingsCopy.load() == candidate, searchPassed, recheckDisplayed, requests == 0 else {
                throw CocoaError(.validationMissingMandatoryProperty)
            }
            let report: [String: Any] = [
                "version": Product.version, "status": "passed", "scope": "native UI, discovery, settings persistence; no host saves",
                "running_application_count": running.count, "unique_application_count": ApplicationDiscovery.candidates(running).count,
                "search_passed": searchPassed, "settings_roundtrip": true, "requests_sent": requests,
                "permission_recheck_displayed": recheckDisplayed,
                "permissions": ["accessibility": lastPermissions.accessibility, "input_monitoring": lastPermissions.listening, "posting": lastPermissions.posting],
                "login_registration_attempted": false, "user_settings_read": false,
                "system_temporary_directory": RecoveryDiscovery.systemTemporaryDirectory().path,
                "screenshots": ["settings-500.png", "settings-460.png", "settings-dark.png", "running-applications.png", "rescue-center.png"]
            ]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
                .write(to: directory.appendingPathComponent("native-smoke.json"))
            print("Native smoke passed; no host saves or login changes.")
        } catch { fputs("Native smoke failed: \(error)\n", stderr); exit(1) }
        NSApp.terminate(nil)
    }
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let delegate = SaveApp()
application.delegate = delegate
application.run()
