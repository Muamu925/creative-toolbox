import AppKit
import ApplicationServices
import Carbon

struct SavePermissions: Equatable {
    var accessibility: Bool
    var listening: Bool
    var posting: Bool
    var ready: Bool { accessibility && listening && posting }
    static func requestAccessibility() {
        _ = AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
    }
    static func requestInputMonitoring() { _ = CGRequestListenEventAccess() }
    static func requestEventPosting() { _ = CGRequestPostEventAccess() }
    static func current() -> SavePermissions {
        SavePermissions(accessibility: AXIsProcessTrusted(),
                        listening: CGPreflightListenEventAccess(),
                        posting: CGPreflightPostEventAccess())
    }
    var description: String {
        "辅助功能：\(accessibility ? "可用" : "未生效")    输入监控：\(listening ? "可用" : "未生效")\n事件发送：\(posting ? "可用" : "未生效")"
    }
    var guidance: String {
        if ready { return "当前进程的自动保存权限已就绪。" }
        if accessibility && listening { return "请点击「事件发送…」申请快捷键发送权限。" }
        return "若系统开关已打开，请退出并重新打开 Autosave Lite。"
    }
}

enum SaveDispatch { case sent, cancelled, unavailable(String) }

struct HardwareInput {
    let idle: Double
    let lastInputTime: Double
    let pressed: Bool
    let activityToken: UInt64
    static func read() -> HardwareInput {
        let idle = CGEventSource.secondsSinceLastEventType(.hidSystemState,
            eventType: CGEventType(rawValue: UInt32.max)!)
        let sampledAt = ProcessInfo.processInfo.systemUptime
        // Pointer movement postpones a request but does not itself dirty a file.
        let editingEvents: [CGEventType] = [.keyDown, .keyUp, .leftMouseDown, .leftMouseUp,
            .rightMouseDown, .rightMouseUp, .otherMouseDown, .otherMouseUp,
            .leftMouseDragged, .rightMouseDragged, .otherMouseDragged, .scrollWheel, .tabletPointer]
        let token = editingEvents.reduce(UInt64(0)) {
            $0 &+ UInt64(CGEventSource.counterForEventType(.hidSystemState, eventType: $1))
        }
        let pressed = (0..<128).contains { CGEventSource.keyState(.hidSystemState, key: CGKeyCode($0)) }
            || (0..<8).contains { CGEventSource.buttonState(.hidSystemState, button: CGMouseButton(rawValue: UInt32($0))!) }
        return HardwareInput(idle: idle, lastInputTime: sampledAt - idle,
                             pressed: pressed, activityToken: token)
    }
    func unchanged(from observation: SaveObservation, idleRequired: Double) -> Bool {
        idle.isFinite && idle >= idleRequired && !pressed && lastInputTime.isFinite
        && abs(lastInputTime - observation.lastInputTime) < 0.02 && activityToken == observation.activityToken
    }
}

// All calls to this object are serialized by the controller's observation queue.
final class MacSaveBackend {
    private(set) var protectedObservations = 0
    private(set) var sendCount = 0
    private var windows: [(AXUIElement, UInt)] = []
    private var nextWindowID: UInt = 1
    let permissionProvider: () -> SavePermissions
    init(permissionProvider: @escaping () -> SavePermissions = SavePermissions.current) {
        self.permissionProvider = permissionProvider
    }
    func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
        return value
    }
    func element(_ object: AXUIElement, _ name: String) -> AXUIElement? {
        guard let value = attribute(object, name), CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
        return unsafeBitCast(value, to: AXUIElement.self)
    }
    private func windowID(_ element: AXUIElement) -> UInt {
        if let entry = windows.first(where: { CFEqual($0.0, element) }) { return entry.1 }
        if windows.count >= 64 { windows.removeFirst() }
        let id = nextWindowID; nextWindowID += 1; windows.append((element, id)); return id
    }
    func observe(session: ApplicationSession, permissions: SavePermissions) -> SaveObservation {
        let bare = SaveTarget(session: session, windowID: 0, title: "", document: "")
        var observation = SaveObservation(target: bare, permitted: permissions.ready)
        // Discovery and binding work without any protected AX/input queries.
        guard permissions.ready && permissionProvider().ready else {
            observation.permitted = false; return observation
        }
        guard let front = NSWorkspace.shared.frontmostApplication,
              ApplicationDiscovery.session(front)?.key == session.key else {
            observation.blocked = "等待已确认的应用回到前台。"; return observation
        }
        protectedObservations += 1
        guard let console = CGSessionCopyCurrentDictionary() as? [String: Any],
              console[kCGSessionOnConsoleKey as String] as? Bool == true,
              console["CGSSessionScreenIsLocked"] as? Bool != true else {
            observation.blocked = "锁屏或非活动会话，自动保存已暂停。"; return observation
        }
        guard !IsSecureEventInputEnabled() else {
            observation.blocked = "系统安全输入已启用，暂不发送快捷键。"; return observation
        }
        let axApp = AXUIElementCreateApplication(session.pid)
        AXUIElementSetMessagingTimeout(axApp, 0.10)
        guard let window = element(axApp, kAXFocusedWindowAttribute) else {
            observation.blocked = "等待打开文档，或宿主暂时未响应。"; return observation
        }
        let title = attribute(window, kAXTitleAttribute) as? String ?? ""
        let rawDocument = attribute(window, kAXDocumentAttribute) as? String ?? ""
        let role = attribute(window, kAXRoleAttribute) as? String
        let subrole = attribute(window, kAXSubroleAttribute) as? String
        // AXSheets is not exported as a constant by all supported SDKs.
        let sheets = attribute(window, "AXSheets") as? [AXUIElement] ?? []
        let children = attribute(window, kAXChildrenAttribute) as? [AXUIElement] ?? []
        let hasSheet = children.prefix(20).contains { attribute($0, kAXRoleAttribute) as? String == kAXSheetRole }
        guard role == kAXWindowRole, subrole != kAXDialogSubrole,
              attribute(window, kAXModalAttribute) as? Bool != true,
              sheets.isEmpty, !hasSheet else {
            observation.blocked = "正在处理对话框，等待返回文档。"; return observation
        }
        guard let document = DocumentRules.localDocument(rawDocument) else {
            observation.blocked = DocumentRules.firstSave(title: title)
                ? "请先手动保存一次，确定文件名称和位置。"
                : "无法确认当前文档的本地保存位置；该窗口暂不自动保存。"
            return observation
        }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: document.path, isDirectory: &isDirectory), !isDirectory.boolValue,
              FileManager.default.isWritableFile(atPath: document.path) else {
            observation.blocked = "文档不存在或不可写，请先在原应用中检查保存位置。"; return observation
        }
        guard let focus = element(axApp, kAXFocusedUIElementAttribute),
              let focusedRole = attribute(focus, kAXRoleAttribute) as? String else {
            observation.blocked = "无法确认当前操作位置，稍后重新检查。"; return observation
        }
        if [kAXTextFieldRole, kAXComboBoxRole, kAXMenuRole, kAXMenuItemRole, kAXMenuBarItemRole].contains(focusedRole) {
            observation.blocked = "输入框或菜单正在使用，等待返回文档。"; return observation
        }
        observation.target = SaveTarget(session: session, windowID: windowID(window),
                                        title: title, document: document.absoluteString)
        observation.edited = attribute(window, kAXEditedAttribute) as? Bool
        let input = HardwareInput.read()
        observation.idle = input.idle; observation.lastInputTime = input.lastInputTime
        observation.pressed = input.pressed; observation.activityToken = input.activityToken
        return observation
    }
    func sendSave(expected: SaveObservation, idleRequired: Double = 3, stillAuthorized: () -> Bool) -> SaveDispatch {
        guard stillAuthorized(), let target = expected.target else { return .cancelled }
        let permissions = permissionProvider()
        guard permissions.ready else { return .unavailable("保存请求未发出：系统权限已变化。") }
        let fresh = observe(session: target.session, permissions: permissions)
        guard SavePolicy.recheck(expected, fresh, idleRequired: idleRequired), stillAuthorized() else { return .cancelled }
        guard let source = CGEventSource(stateID: .privateState) else {
            return .unavailable("无法创建保存快捷键事件源。")
        }
        source.userData = 0x4155544F53415645
        guard let down = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_S), keyDown: true),
              let up = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_S), keyDown: false) else {
            return .unavailable("无法创建保存快捷键事件。")
        }
        down.flags = .maskCommand; up.flags = .maskCommand
        // Recheck the foreground immediately after AX work, which can time out.
        guard stillAuthorized(), ApplicationDiscovery.session(NSWorkspace.shared.frontmostApplication ?? NSRunningApplication.current)?.key == target.processKey else {
            return .cancelled
        }
        guard permissionProvider().ready else { return .unavailable("系统权限已变化，保存请求已取消。") }
        guard HardwareInput.read().unchanged(from: fresh, idleRequired: idleRequired), stillAuthorized() else { return .cancelled }
        down.postToPid(target.session.pid)
        up.postToPid(target.session.pid)
        sendCount += 1
        return .sent
    }
}

// The main thread invalidates a ticket on any lifecycle, pause or selection
// change; the serial worker checks it again immediately before dispatch.
final class DispatchGate {
    private let lock = NSLock()
    private var generation: UInt64 = 0
    func invalidate() { lock.lock(); generation &+= 1; lock.unlock() }
    func ticket() -> UInt64 { lock.lock(); defer { lock.unlock() }; return generation }
    func valid(_ ticket: UInt64) -> Bool { lock.lock(); defer { lock.unlock() }; return generation == ticket }
}
