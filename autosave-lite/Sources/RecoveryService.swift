import Foundation
import CryptoKit
import Darwin

struct RecoverySource {
    let name: String
    let url: URL
}

enum RecoveryDiscovery {
    static func systemTemporaryDirectory() -> URL {
        FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
    }
    static let supported = [
        DesignApp(id: "com.adobe.illustrator", name: "Illustrator"),
        DesignApp(id: "com.adobe.Photoshop", name: "Photoshop")
    ]
    static func sources(for id: String, home: URL = FileManager.default.homeDirectoryForCurrentUser) -> [RecoverySource] {
        let fm = FileManager.default
        func children(_ url: URL) -> [URL] {
            (try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [])) ?? []
        }
        let preferences = home.appendingPathComponent("Library/Preferences")
        var result: [URL] = []
        if id == "com.adobe.illustrator" {
            for version in children(preferences) where version.lastPathComponent.hasPrefix("Adobe Illustrator ") && version.lastPathComponent.hasSuffix(" Settings") {
                result.append(version.appendingPathComponent("DataRecovery"))
                for locale in children(version) where locale.lastPathComponent.range(of: "^[a-z]{2}[_-][A-Za-z]{2,4}$", options: .regularExpression) != nil {
                    result.append(locale.appendingPathComponent("DataRecovery"))
                }
            }
        } else if id == "com.adobe.Photoshop" {
            let support = home.appendingPathComponent("Library/Application Support/Adobe")
            for version in children(support) where version.lastPathComponent.hasPrefix("Adobe Photoshop ") {
                result.append(version.appendingPathComponent("AutoRecover"))
            }
            for version in children(preferences) where version.lastPathComponent.hasPrefix("Adobe Photoshop ") && version.lastPathComponent.hasSuffix(" Settings") {
                result.append(version.appendingPathComponent("AutoRecover"))
            }
        }
        return result.filter { fm.fileExists(atPath: $0.path) }
            .sorted { $0.path < $1.path }.map { RecoverySource(name: $0.deletingLastPathComponent().lastPathComponent, url: $0) }
    }
}

struct RecoveryFile: Codable {
    let source: String
    let stored: String
    let bytes: Int64
    let sha256: String
}
struct RecoveryOutput: Codable {
    let path: String
    let bytes: Int64
    let sha256: String
    let recordedAt: String
    var contentConfirmed: Bool
}
struct RecoveryManifest: Codable {
    var schema = 1
    var id: String
    var createdAt: String
    var applicationID: String
    var applicationName: String
    var reason: String
    var sourceRoots: [String]
    var files: [RecoveryFile]
    var warnings: [String]
    var consistency: String
    var output: RecoveryOutput?
    var stage: String { output?.contentConfirmed == true ? "内容已确认" : output != nil ? "已记录另存文件，待确认内容" : consistency == "verified" ? "快照副本校验通过" : "快照需检查" }
}
struct RecoverySnapshot {
    let directory: URL
    var manifest: RecoveryManifest
}
enum RecoveryFailure: LocalizedError {
    case noData, limit(String), invalid(String)
    var errorDescription: String? {
        switch self {
        case .noData: return "未发现可保留的恢复数据。空目录不代表存在可恢复文档。"
        case .limit(let message), .invalid(let message): return message
        }
    }
}

// Serial, on-demand file work. Never deletes, renames or writes into a source.
final class RecoveryService {
    struct Entry {
        let source: URL
        let relative: String
        let bytes: Int64
        let modified: Double
        var stamp: String { "\(relative)|\(bytes)|\(modified)" }
    }
    let storage: URL
    let byteLimit: Int64
    let vaultLimit: Int64
    let fileLimit: Int
    init(storage: URL, byteLimit: Int64 = 2_147_483_648, vaultLimit: Int64 = 5_368_709_120, fileLimit: Int = 20_000) {
        self.storage = storage.standardizedFileURL.resolvingSymlinksInPath()
        self.byteLimit = byteLimit; self.vaultLimit = vaultLimit; self.fileLimit = fileLimit
    }
    private func inventory(_ sources: [RecoverySource], warnings: inout [String]) throws -> [Entry] {
        var result: [Entry] = []
        var total: Int64 = 0
        var enumerationWarnings: [String] = []
        defer { warnings.append(contentsOf: enumerationWarnings) }
        let fm = FileManager.default
        for (index, source) in sources.enumerated() {
            let original = source.url.standardizedFileURL
            guard try original.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink != true else {
                warnings.append("已跳过符号链接：\(original.path)"); continue
            }
            let root = original.resolvingSymlinksInPath()
            let resolved = root
            let destination = storage.resolvingSymlinksInPath()
            guard resolved.path != destination.path && !destination.path.hasPrefix(resolved.path + "/") else {
                throw RecoveryFailure.invalid("快照位置不能位于待保留的源目录内。")
            }
            let values = try root.resourceValues(forKeys: [.isSymbolicLinkKey, .isDirectoryKey, .isRegularFileKey])
            guard values.isSymbolicLink != true else { warnings.append("已跳过符号链接：\(root.path)"); continue }
            var urls: [URL] = []
            if values.isRegularFile == true { urls = [root] }
            else if values.isDirectory == true {
                guard let enumerator = fm.enumerator(at: root,
                    includingPropertiesForKeys: [.isSymbolicLinkKey, .isRegularFileKey, .isDirectoryKey, .fileSizeKey, .contentModificationDateKey],
                    options: [], errorHandler: { url, error in enumerationWarnings.append("\(url.path)：\(error.localizedDescription)"); return true }) else {
                    warnings.append("无法列出目录：\(root.path)"); continue
                }
                for case let url as URL in enumerator {
                    let v = try url.resourceValues(forKeys: [.isSymbolicLinkKey, .isRegularFileKey])
                    if v.isSymbolicLink == true { warnings.append("已跳过符号链接：\(url.path)"); enumerator.skipDescendants(); continue }
                    if v.isRegularFile == true { urls.append(url) }
                    if urls.count > fileLimit { throw RecoveryFailure.limit("恢复资料文件过多，请选择更具体的恢复目录。") }
                }
            }
            for url in urls {
                let v = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                let size = Int64(v.fileSize ?? 0); total += size
                guard total <= byteLimit && result.count < fileLimit else { throw RecoveryFailure.limit("本次恢复资料超过快照限额，请使用外置磁盘手动保留完整目录。") }
                let canonical = url.resolvingSymlinksInPath().path
                guard values.isRegularFile == true || canonical.hasPrefix(root.path + "/") else {
                    throw RecoveryFailure.invalid("源目录路径发生变化，请重新检查恢复资料。")
                }
                let child = values.isRegularFile == true ? root.lastPathComponent : String(canonical.dropFirst(root.path.count + 1))
                result.append(Entry(source: url, relative: String(format: "source-%02d/", index + 1) + child,
                                    bytes: size, modified: v.contentModificationDate?.timeIntervalSince1970 ?? 0))
            }
        }
        return result.sorted { $0.relative < $1.relative }
    }
    static func digest(_ url: URL) throws -> (Int64, String) {
        let fd = Darwin.open(url.path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw RecoveryFailure.invalid("无法读取文件：\(url.lastPathComponent)") }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        defer { try? handle.close() }
        var statbuf = stat()
        guard fstat(fd, &statbuf) == 0, statbuf.st_mode & S_IFMT == S_IFREG else {
            throw RecoveryFailure.invalid("所选路径不是普通文件。")
        }
        var hash = SHA256(); var count: Int64 = 0
        while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty {
            hash.update(data: data); count += Int64(data.count)
        }
        return (count, hash.finalize().map { String(format: "%02x", $0) }.joined())
    }
    private func copy(_ entry: Entry, to destination: URL) throws -> RecoveryFile {
        try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        let fd = Darwin.open(entry.source.path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw RecoveryFailure.invalid("源文件已移除或无法读取：\(entry.source.lastPathComponent)") }
        let input = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        defer { try? input.close() }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_mode & S_IFMT == S_IFREG else { throw RecoveryFailure.invalid("源路径不再是普通文件。") }
        guard FileManager.default.createFile(atPath: destination.path, contents: nil) else { throw CocoaError(.fileWriteUnknown) }
        let output = try FileHandle(forWritingTo: destination)
        defer { try? output.close() }
        var hash = SHA256(); var count: Int64 = 0
        while let data = try input.read(upToCount: 1_048_576), !data.isEmpty {
            count += Int64(data.count)
            guard count <= entry.bytes && count <= byteLimit else { throw RecoveryFailure.limit("源文件持续增长，已停止本次复制。") }
            try output.write(contentsOf: data); hash.update(data: data)
        }
        try output.synchronize()
        let digest = hash.finalize().map { String(format: "%02x", $0) }.joined()
        let verification = try Self.digest(destination)
        guard verification.0 == count, verification.1 == digest else { throw RecoveryFailure.invalid("快照文件校验失败。") }
        return RecoveryFile(source: entry.source.path, stored: entry.relative, bytes: count, sha256: digest)
    }
    func snapshots() -> [RecoverySnapshot] {
        let fm = FileManager.default
        let directories = (try? fm.contentsOfDirectory(at: storage, includingPropertiesForKeys: [.isDirectoryKey])) ?? []
        return directories.compactMap { dir in
            guard let data = try? Data(contentsOf: dir.appendingPathComponent("manifest.json")), data.count <= 20_000_000,
                  let manifest = try? JSONDecoder().decode(RecoveryManifest.self, from: data), manifest.schema == 1 else { return nil }
            return RecoverySnapshot(directory: dir, manifest: manifest)
        }.sorted { $0.manifest.createdAt > $1.manifest.createdAt }
    }
    func capture(applicationID: String, name: String, sources: [RecoverySource], reason: String,
                 progress: ((Int, Int) -> Void)? = nil) throws -> RecoverySnapshot {
        var warnings: [String] = []
        let entries = try inventory(sources, warnings: &warnings)
        guard !entries.isEmpty else { throw RecoveryFailure.noData }
        let total = entries.reduce(Int64(0)) { $0 + $1.bytes }
        var existing: Int64 = 0
        if let enumeration = FileManager.default.enumerator(at: storage, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey]) {
            for case let url as URL in enumeration {
                let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
                if values.isSymbolicLink == true { enumeration.skipDescendants(); continue }
                if values.isRegularFile == true { existing += Int64(values.fileSize ?? 0) }
            }
        }
        guard existing + total <= vaultLimit else { throw RecoveryFailure.limit("恢复快照已达到空间限额。请先整理已有快照或选择其他保存位置；程序不会自动删除恢复资料。") }
        try FileManager.default.createDirectory(at: storage, withIntermediateDirectories: true)
        let volume = try FileManager.default.attributesOfFileSystem(forPath: storage.path)
        guard let capacity = volume[.systemFreeSize] as? NSNumber else {
            throw RecoveryFailure.invalid("无法检查快照位置的剩余空间。")
        }
        let available = capacity.int64Value
        if available < total + 104_857_600 { throw RecoveryFailure.limit("快照位置空间不足，请选择其他保存位置。") }
        let date = Date(); let formatter = DateFormatter(); formatter.dateFormat = "yyyyMMdd-HHmmss"
        let id = UUID().uuidString
        let directory = storage.appendingPathComponent(formatter.string(from: date) + "-" + String(id.prefix(8)), isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        var manifest = RecoveryManifest(id: id, createdAt: ISO8601DateFormatter().string(from: date),
            applicationID: applicationID, applicationName: name, reason: reason,
            sourceRoots: sources.map { $0.url.path }, files: [], warnings: [], consistency: "incomplete")
        try write(manifest, in: directory)
        for entry in entries {
            do {
                let copied = try copy(entry, to: directory.appendingPathComponent(entry.relative))
                manifest.files.append(copied)
                progress?(manifest.files.count, entries.count)
                let sourceAfter = try Self.digest(entry.source)
                if sourceAfter.0 != copied.bytes || sourceAfter.1 != copied.sha256 {
                    warnings.append("复制过程中源文件发生变化：\(entry.source.path)")
                }
            } catch { warnings.append("\(entry.source.path)：\(error.localizedDescription)") }
        }
        do {
            let after = try inventory(sources, warnings: &warnings)
            if entries.map(\.stamp) != after.map(\.stamp) { warnings.append("复制期间源目录结构或文件状态发生变化。") }
        } catch { warnings.append("无法完成源目录复核：\(error.localizedDescription)") }
        manifest.warnings = warnings
        manifest.consistency = warnings.isEmpty && manifest.files.count == entries.count ? "verified" : "needs_review"
        try write(manifest, in: directory)
        return RecoverySnapshot(directory: directory, manifest: manifest)
    }
    func write(_ manifest: RecoveryManifest, in directory: URL) throws {
        guard directory.deletingLastPathComponent().standardizedFileURL.resolvingSymlinksInPath().path == storage.path else { throw RecoveryFailure.invalid("无效的快照记录位置。") }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(manifest).write(to: directory.appendingPathComponent("manifest.json"), options: .atomic)
    }
    func recordOutput(_ file: URL, snapshot: RecoverySnapshot) throws -> RecoverySnapshot {
        let url = file.standardizedFileURL.resolvingSymlinksInPath()
        guard !snapshot.manifest.files.contains(where: { URL(fileURLWithPath: $0.source).resolvingSymlinksInPath() == url }),
              !url.path.hasPrefix(storage.resolvingSymlinksInPath().path + "/") else {
            throw RecoveryFailure.invalid("请选择另存的新文件，不要选择原文件或快照内的文件。")
        }
        let metadata = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        let digest = try Self.digest(url)
        let after = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        guard metadata.fileSize == after.fileSize, metadata.contentModificationDate == after.contentModificationDate else {
            throw RecoveryFailure.invalid("文件仍在写入，请等待原应用保存完成后重试。")
        }
        var updated = snapshot
        updated.manifest.output = RecoveryOutput(path: url.path, bytes: digest.0, sha256: digest.1,
            recordedAt: ISO8601DateFormatter().string(from: Date()), contentConfirmed: false)
        try write(updated.manifest, in: updated.directory); return updated
    }
    func confirmContent(_ snapshot: RecoverySnapshot) throws -> RecoverySnapshot {
        guard let output = snapshot.manifest.output else { throw RecoveryFailure.invalid("请先记录另存的新文件，再确认内容。") }
        let current = try Self.digest(URL(fileURLWithPath: output.path))
        guard current.0 == output.bytes && current.1 == output.sha256 else {
            throw RecoveryFailure.invalid("另存文件已变化，请重新记录文件后确认内容。")
        }
        var updated = snapshot; updated.manifest.output?.contentConfirmed = true
        try write(updated.manifest, in: updated.directory); return updated
    }
}
