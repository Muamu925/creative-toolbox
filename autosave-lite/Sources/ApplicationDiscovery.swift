import AppKit

struct DiscoveredApplication {
    let id: String
    let name: String
    let path: String
    let session: ApplicationSession?
}

enum DiscoveryError: LocalizedError {
    case invalidBundle, missingID, ownApplication, invalidIdentity
    var errorDescription: String? {
        switch self {
        case .invalidBundle: return "所选文件不是有效的 Mac 应用。"
        case .missingID: return "无法读取应用标识，请选择原始 .app 文件。"
        case .ownApplication: return "自动保存工具不能添加自身。"
        case .invalidIdentity: return "应用标识不符合设置格式。"
        }
    }
}

enum ApplicationDiscovery {
    static func session(_ app: NSRunningApplication) -> ApplicationSession? {
        guard !app.isTerminated, app.activationPolicy == .regular,
              app.processIdentifier != getpid(), let id = app.bundleIdentifier,
              SaveSettings.validID(id), let launch = app.launchDate else { return nil }
        return ApplicationSession(id: id, name: app.localizedName ?? DesignApp.name(id),
                                  pid: app.processIdentifier,
                                  launch: String(format: "%.6f", launch.timeIntervalSince1970))
    }
    static func running() -> [DiscoveredApplication] {
        NSWorkspace.shared.runningApplications.compactMap { app in
            guard let session = session(app), let url = app.bundleURL else { return nil }
            return DiscoveredApplication(id: session.id, name: session.name, path: url.path, session: session)
        }
    }
    static func candidates(_ applications: [DiscoveredApplication], query: String = "") -> [DiscoveredApplication] {
        var seen = Set<String>()
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return applications.sorted { $0.name == $1.name ? $0.path < $1.path : $0.name.localizedStandardCompare($1.name) == .orderedAscending }
            .filter { app in
                guard SaveSettings.validID(app.id), seen.insert(app.id).inserted else { return false }
                return needle.isEmpty || app.name.localizedCaseInsensitiveContains(needle)
                    || app.id.localizedCaseInsensitiveContains(needle)
            }
    }
    static func fromBundle(_ url: URL) throws -> DiscoveredApplication {
        guard url.pathExtension.lowercased() == "app", let bundle = Bundle(url: url),
              bundle.object(forInfoDictionaryKey: "CFBundlePackageType") as? String == "APPL" else {
            throw DiscoveryError.invalidBundle
        }
        guard let id = bundle.bundleIdentifier, !id.isEmpty else { throw DiscoveryError.missingID }
        guard id != Product.bundleID else { throw DiscoveryError.ownApplication }
        guard SaveSettings.validID(id) else { throw DiscoveryError.invalidIdentity }
        let name = (bundle.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String)
            ?? (bundle.object(forInfoDictionaryKey: "CFBundleName") as? String)
            ?? url.deletingPathExtension().lastPathComponent
        return DiscoveredApplication(id: id, name: name, path: url.standardizedFileURL.path, session: nil)
    }
}
