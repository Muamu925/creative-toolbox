import Foundation

enum Product {
    static let version = "0.1.2"
    static let bundleID = "org.creativetoolbox.autosave-lite"
}

struct DesignApp {
    let id: String
    let name: String
    static let presets = [
        DesignApp(id: "com.adobe.illustrator", name: "Illustrator"),
        DesignApp(id: "com.adobe.Photoshop", name: "Photoshop"),
        DesignApp(id: "com.adobe.InDesign", name: "InDesign"),
        DesignApp(id: "com.bohemiancoding.sketch3", name: "Sketch"),
        DesignApp(id: "com.seriflabs.affinitydesigner2", name: "Affinity Designer 2"),
        DesignApp(id: "com.seriflabs.affinityphoto2", name: "Affinity Photo 2")
    ]
    static func name(_ id: String) -> String { presets.first { $0.id == id }?.name ?? id }
}

struct SaveSettings: Codable, Equatable {
    var schema = 1
    var enabled = true
    var interval = 60
    var idleSeconds = 3
    var rescueEnabled = true
    var rescueDirectory: String?
    var applications = ["com.adobe.illustrator", "com.adobe.Photoshop"]
    var customNames: [String: String] = [:]
    var applicationPaths: [String: String] = [:]
    static let intervals = [30, 60, 120, 300]
    static let idleOptions = [3, 5, 10]
    static func validID(_ id: String) -> Bool {
        !id.isEmpty && id.count <= 255 && id != Product.bundleID
        && id.range(of: "^[A-Za-z0-9_.-]+$", options: .regularExpression) != nil
    }
    var valid: Bool {
        schema == 1 && Self.intervals.contains(interval) && Self.idleOptions.contains(idleSeconds) && applications.count <= 100
        && Set(applications).count == applications.count && applications.allSatisfy(Self.validID)
        && customNames.count <= 100 && customNames.keys.allSatisfy(Self.validID)
        && customNames.values.allSatisfy { !$0.isEmpty && $0.count <= 256 }
        && applicationPaths.count <= 100 && applicationPaths.keys.allSatisfy(Self.validID)
        && applicationPaths.values.allSatisfy { $0.hasPrefix("/") && $0.count <= 4096 }
        && (rescueDirectory == nil || (rescueDirectory!.hasPrefix("/") && rescueDirectory!.count <= 4096))
    }
    enum CodingKeys: String, CodingKey { case schema, enabled, interval, idleSeconds, rescueEnabled, rescueDirectory, applications, customNames, applicationPaths }
    init() {}
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        schema = try c.decode(Int.self, forKey: .schema)
        enabled = try c.decode(Bool.self, forKey: .enabled)
        interval = try c.decode(Int.self, forKey: .interval)
        idleSeconds = try c.decodeIfPresent(Int.self, forKey: .idleSeconds) ?? 3
        rescueEnabled = try c.decodeIfPresent(Bool.self, forKey: .rescueEnabled) ?? true
        rescueDirectory = try c.decodeIfPresent(String.self, forKey: .rescueDirectory)
        applications = try c.decode([String].self, forKey: .applications)
        customNames = try c.decodeIfPresent([String: String].self, forKey: .customNames) ?? [:]
        applicationPaths = try c.decodeIfPresent([String: String].self, forKey: .applicationPaths) ?? [:]
    }
}

final class SettingsStore {
    let url: URL
    private(set) var warning: String?
    init(url: URL) { self.url = url }
    func load() -> SaveSettings {
        guard FileManager.default.fileExists(atPath: url.path) else { return SaveSettings() }
        do {
            let data = try Data(contentsOf: url)
            guard data.count <= 524_288 else { throw CocoaError(.fileReadCorruptFile) }
            let value = try JSONDecoder().decode(SaveSettings.self, from: data)
            guard value.valid else { throw CocoaError(.fileReadCorruptFile) }
            warning = nil
            return value
        } catch {
            warning = "设置未能载入，检测已暂停。原设置文件已保留。"
            var value = SaveSettings(); value.enabled = false; return value
        }
    }
    func save(_ value: SaveSettings) throws {
        guard value.valid else { throw CocoaError(.fileWriteInvalidFileName) }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(value)
        guard data.count <= 524_288 else { throw CocoaError(.fileWriteInvalidFileName) }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url, options: .atomic)
        warning = nil
    }
}

struct ApplicationSession: Equatable, Hashable {
    let id: String
    let name: String
    let pid: Int32
    let launch: String
    var key: String { "\(id):\(pid):\(launch)" }
}
enum SessionChoice { case pending, approved, declined }

final class SessionRegistry {
    private(set) var sessions: [String: ApplicationSession] = [:]
    private(set) var choices: [String: SessionChoice] = [:]
    private var order: [String] = []
    @discardableResult
    func reconcile(running: [ApplicationSession], selected: Set<String>) -> Set<String> {
        let live = Dictionary(running.filter { selected.contains($0.id) }.map { ($0.key, $0) },
                              uniquingKeysWith: { first, _ in first })
        let ended = Set(sessions.keys).subtracting(live.keys)
        for key in ended { choices.removeValue(forKey: key) }
        order.removeAll { live[$0] == nil }
        for session in live.values.sorted(by: { $0.name == $1.name ? $0.key < $1.key : $0.name < $1.name }) where choices[session.key] == nil {
            choices[session.key] = .pending; order.append(session.key)
        }
        sessions = live
        return ended
    }
    var nextPending: ApplicationSession? { order.first { choices[$0] == .pending }.flatMap { sessions[$0] } }
    func decide(_ session: ApplicationSession, approved: Bool) {
        guard sessions[session.key] != nil else { return }
        choices[session.key] = approved ? .approved : .declined
    }
    func requestAgain(_ session: ApplicationSession) {
        guard sessions[session.key] != nil else { return }
        choices[session.key] = .pending
    }
    var approvedKeys: Set<String> { Set(choices.filter { $0.value == .approved }.map(\.key)) }
    var approvedCount: Int { approvedKeys.count }
}

struct SaveTarget: Equatable {
    let session: ApplicationSession
    let windowID: UInt
    let title: String
    let document: String
    var processKey: String { session.key }
    var windowKey: String { "\(processKey):\(windowID):\(document)" }
}

struct SaveObservation {
    var target: SaveTarget?
    var permitted = false
    var idle = 0.0
    var pressed = false
    var blocked: String?
    var lastInputTime = 0.0
    var activityToken: UInt64?
    var edited: Bool?
}

struct SaveDecision {
    let code: String
    let message: String
    var due = false
}

final class SavePolicy {
    static let idleRequired = 3.0
    private struct DocumentState {
        var pending = true
        var lastInput = -Double.infinity
        var lastActivityToken: UInt64?
        var wasClean = false
    }
    private var attempts: [String: Double] = [:]
    private var documents: [String: DocumentState] = [:]
    private var retries: [String: Double] = [:]
    private var stableKey: String?
    private var stableSince = 0.0
    private var lastTick: Double?

    func reset() { attempts.removeAll(); documents.removeAll(); retries.removeAll(); invalidateForeground(); lastTick = nil }
    func invalidateForeground() { stableKey = nil }
    func ended(processKey: String) {
        attempts.removeValue(forKey: processKey); retries.removeValue(forKey: processKey)
        documents = documents.filter { !$0.key.hasPrefix(processKey + ":") }
        if stableKey?.hasPrefix(processKey + ":") == true { invalidateForeground() }
    }
    func evaluate(_ observation: SaveObservation, settings: SaveSettings, now: Double,
                  ownPID: Int32, approved: Set<String>) -> SaveDecision {
        guard now.isFinite else { return SaveDecision(code: "unknown", message: "无法确认计时状态。") }
        if let lastTick, now < lastTick { reset() }
        lastTick = now
        guard settings.enabled else { invalidateForeground(); return SaveDecision(code: "paused", message: "检测已暂停。") }
        guard settings.valid else { return SaveDecision(code: "invalid", message: "设置无效，请重新配置。") }
        guard let target = observation.target, target.session.pid != ownPID,
              settings.applications.contains(target.session.id), approved.contains(target.processKey) else {
            invalidateForeground(); return SaveDecision(code: "waiting", message: "等待已确认的应用回到前台。")
        }
        guard observation.permitted else {
            invalidateForeground(); return SaveDecision(code: "permission", message: "本次已同意，自动保存待授权。")
        }
        guard observation.idle.isFinite, observation.idle >= 0, observation.lastInputTime.isFinite else {
            invalidateForeground(); return SaveDecision(code: "unknown", message: "暂时无法确认输入状态。")
        }
        if let blocked = observation.blocked {
            invalidateForeground(); return SaveDecision(code: "blocked", message: blocked)
        }
        if stableKey != target.windowKey { stableKey = target.windowKey; stableSince = now }
        if attempts[target.processKey] == nil { attempts[target.processKey] = now }
        var document = documents[target.windowKey] ?? DocumentState()
        // HID state excludes this utility's private event source. Never discard
        // a time window: genuine input immediately after a request must survive.
        let newActivity = observation.activityToken.map { $0 != document.lastActivityToken }
            ?? (observation.lastInputTime > document.lastInput + 0.02)
        if newActivity { document.pending = true }
        document.lastActivityToken = observation.activityToken
        document.lastInput = observation.lastInputTime
        if observation.edited == false { document.pending = false; document.wasClean = true }
        if observation.edited == true && document.wasClean { document.pending = true; document.wasClean = false }
        if documents.count >= 256 && documents[target.windowKey] == nil { documents.removeAll() }
        documents[target.windowKey] = document
        guard now - stableSince >= Double(settings.idleSeconds) else { return SaveDecision(code: "switching", message: "文档刚刚切换，正在重新确认空闲状态。") }
        guard document.pending else { return SaveDecision(code: "unchanged", message: "本轮已检查，等待后续操作。") }
        guard now - attempts[target.processKey]! >= Double(settings.interval) else {
            return SaveDecision(code: "interval", message: "等待保存间隔达到 \(settings.interval) 秒。")
        }
        guard !observation.pressed, observation.idle >= Double(settings.idleSeconds) else {
            return SaveDecision(code: "editing", message: "正在操作，等待连续空闲 \(settings.idleSeconds) 秒。")
        }
        guard now >= retries[target.processKey, default: 0] else {
            return SaveDecision(code: "retry", message: "稍后重新检查保存条件。")
        }
        return SaveDecision(code: "ready", message: "正在复核当前文档。", due: true)
    }
    func sent(_ observation: SaveObservation, now: Double) {
        guard let target = observation.target else { return }
        attempts[target.processKey] = now
        var document = documents[target.windowKey] ?? DocumentState()
        document.pending = false; document.lastInput = observation.lastInputTime; document.wasClean = false
        document.lastActivityToken = observation.activityToken
        documents[target.windowKey] = document
    }
    func cancelled(processKey: String, now: Double) { retries[processKey] = now + 3; invalidateForeground() }
    static func recheck(_ expected: SaveObservation, _ current: SaveObservation, idleRequired: Double = 3) -> Bool {
        guard let old = expected.target, let new = current.target else { return false }
        return old.session.key == new.session.key && old.windowID == new.windowID && old.document == new.document
        && current.permitted && current.blocked == nil && !current.pressed
        && current.idle.isFinite && current.idle >= idleRequired
        && current.lastInputTime.isFinite && abs(current.lastInputTime - expected.lastInputTime) < 0.02
        && current.activityToken == expected.activityToken
        && current.edited != false
    }
}

enum DocumentRules {
    static func firstSave(title: String) -> Bool {
        let value = title.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return value.isEmpty || ["untitled", "未命名", "无标题", "無標題", "未標題", "未标题"].contains { value.hasPrefix($0) }
    }
    static func localDocument(_ raw: String) -> URL? {
        guard !raw.isEmpty else { return nil }
        if raw.hasPrefix("/") { return URL(fileURLWithPath: raw).standardizedFileURL }
        guard let url = URL(string: raw), url.isFileURL else { return nil }
        return url.standardizedFileURL
    }
}
