import Foundation
import AppKit

struct Failure: Error, CustomStringConvertible { let description: String }
var passed = 0
var failed = 0
func expect(_ condition: @autoclosure () -> Bool, _ message: String = "expectation failed",
            file: String = #file, line: Int = #line) throws {
    if !condition() { throw Failure(description: "\(file):\(line): \(message)") }
}
func test(_ name: String, _ body: () throws -> Void) {
    do { try body(); passed += 1; print("PASS \(name)") }
    catch { failed += 1; print("FAIL \(name): \(error)") }
}
let ai = ApplicationSession(id: "com.adobe.illustrator", name: "Illustrator", pid: 12345, launch: "100")
let ps = ApplicationSession(id: "com.adobe.Photoshop", name: "Photoshop", pid: 12346, launch: "200")
func observation(_ session: ApplicationSession = ai, window: UInt = 1, document: String = "file:///tmp/a.ai",
                 title: String = "a.ai", input: Double = 90, idle: Double = 10) -> SaveObservation {
    var value = SaveObservation()
    value.target = SaveTarget(session: session, windowID: window, title: title, document: document)
    value.permitted = true; value.idle = idle; value.lastInputTime = input
    return value
}
func decision(_ policy: SavePolicy, _ value: SaveObservation = observation(), at now: Double,
              settings: SaveSettings = SaveSettings(), approved: Set<String> = [ai.key, ps.key]) -> SaveDecision {
    policy.evaluate(value, settings: settings, now: now, ownPID: 1, approved: approved)
}
func primed() -> SavePolicy {
    let p = SavePolicy(); _ = decision(p, at: 100); return p
}
let temp = FileManager.default.temporaryDirectory.appendingPathComponent("autosave-tests-\(UUID().uuidString)")
try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: temp) }

test("default settings and intervals") {
    let s = SaveSettings(); try expect(s.valid && s.interval == 60 && SavePolicy.idleRequired == 3)
    try expect(s.applications == [ai.id, ps.id])
}
for seconds in [30, 60, 120, 300] {
    test("interval boundary \(seconds)") {
        var s = SaveSettings(); s.interval = seconds
        let p = SavePolicy(); _ = decision(p, at: 100, settings: s)
        try expect(!decision(p, at: 100 + Double(seconds) - 0.01, settings: s).due)
        try expect(decision(p, at: 100 + Double(seconds), settings: s).due)
    }
}
test("invalid interval rejected") {
    var s = SaveSettings(); s.interval = 0; try expect(!s.valid)
    try expect(!decision(primed(), at: 160, settings: s).due)
}
test("self and duplicate selections rejected") {
    var s = SaveSettings(); s.applications = [Product.bundleID]; try expect(!s.valid)
    s.applications = [ai.id, ai.id]; try expect(!s.valid)
    s.applications = ["bad\nid"]; try expect(!s.valid)
}
test("settings roundtrip and no consent persisted") {
    let store = SettingsStore(url: temp.appendingPathComponent("settings.json"))
    var s = SaveSettings(); s.customNames[ai.id] = "Illustrator 测试"; s.applicationPaths[ai.id] = "/Applications/Test.app"
    try store.save(s); try expect(store.load() == s)
    let bytes = try String(contentsOf: store.url, encoding: .utf8)
    try expect(!bytes.contains("approved") && !bytes.contains("pid") && !bytes.contains("launch"))
}
test("corrupt settings retained and paused") {
    let url = temp.appendingPathComponent("corrupt.json"); let original = Data("broken".utf8)
    try original.write(to: url)
    let store = SettingsStore(url: url); try expect(!store.load().enabled && store.warning != nil)
    let unchanged = try Data(contentsOf: url); try expect(unchanged == original)
}
test("unknown schema pauses") {
    let url = temp.appendingPathComponent("unknown.json")
    try Data(#"{"schema":9,"enabled":true,"interval":60,"applications":[]}"#.utf8).write(to: url)
    try expect(!SettingsStore(url: url).load().enabled)
}
test("draft settings without paths remain compatible") {
    let url = temp.appendingPathComponent("draft.json")
    try Data(#"{"schema":1,"enabled":true,"interval":60,"applications":["com.adobe.illustrator"]}"#.utf8).write(to: url)
    let store = SettingsStore(url: url); try expect(store.load().valid && store.warning == nil)
}
test("invalid writes do not replace good settings") {
    let store = SettingsStore(url: temp.appendingPathComponent("good.json")); let good = SaveSettings()
    try store.save(good); var bad = good; bad.interval = -10
    do { try store.save(bad); throw Failure(description: "invalid write succeeded") }
    catch is CocoaError {}
    try expect(store.load() == good)
}
test("filesystem write failure is reported") {
    let file = temp.appendingPathComponent("not-directory"); try Data().write(to: file)
    do { try SettingsStore(url: file.appendingPathComponent("settings.json")).save(SaveSettings()); throw Failure(description: "write succeeded") }
    catch is CocoaError {}
}
test("application count bounded") {
    var s = SaveSettings(); s.applications = (0..<101).map { "test.app.\($0)" }; try expect(!s.valid)
}
test("first eligible window starts the timer") {
    let p = SavePolicy(); try expect(!decision(p, at: 500).due)
    try expect(decision(p, at: 560).due)
}
test("blocked window does not start timer") {
    let p = SavePolicy(); var o = observation(); o.blocked = "dialog"
    _ = decision(p, o, at: 100)
    try expect(!decision(p, at: 160).due)
    try expect(decision(p, at: 220).due)
}
test("unapproved session never sends") {
    try expect(!decision(primed(), at: 160, approved: []).due)
}
test("unselected target never sends") {
    var s = SaveSettings(); s.applications = [ps.id]
    try expect(!decision(primed(), at: 160, settings: s).due)
}
test("own process never sends") {
    let p = primed()
    try expect(!p.evaluate(observation(), settings: SaveSettings(), now: 160, ownPID: ai.pid, approved: [ai.key]).due)
}
test("paused detection never sends") {
    var s = SaveSettings(); s.enabled = false; try expect(!decision(primed(), at: 160, settings: s).due)
}
test("permission loss cancels and restore stabilizes") {
    let p = primed(); var o = observation(); o.permitted = false
    try expect(decision(p, o, at: 160).code == "permission")
    try expect(!decision(p, at: 161).due); try expect(decision(p, at: 164).due)
}
for idle in [0.0, 2.99, -1.0, Double.nan, Double.infinity] {
    test("unsafe idle \(idle) prevents send") {
        let p = primed(); var o = observation(); o.idle = idle; try expect(!decision(p, o, at: 160).due)
    }
}
test("held key or mouse prevents send") {
    var o = observation(); o.pressed = true; try expect(!decision(primed(), o, at: 160).due)
}
test("exactly three seconds idle qualifies") {
    var o = observation(); o.idle = 3; try expect(decision(primed(), o, at: 160).due)
}
test("title changes do not restart interval") {
    let p = primed(); let o = observation(title: "a.ai *")
    _ = decision(p, o, at: 130); try expect(decision(p, o, at: 160).due)
}
test("no new input produces one request only") {
    let p = primed(); let o = observation()
    try expect(decision(p, o, at: 160).due); p.sent(o, now: 160)
    try expect(!decision(p, o, at: 220).due && !decision(p, o, at: 1000).due)
}
test("real input immediately after a request is retained") {
    let p = primed(); p.sent(observation(), now: 160)
    let o = observation(input: 160.01)
    try expect(!decision(p, o, at: 161).due)
    try expect(decision(p, o, at: 220).due)
}
test("clean document suppresses unnecessary requests") {
    let p = primed(); var o = observation(); o.edited = false
    try expect(!decision(p, o, at: 160).due)
    o.edited = true
    try expect(decision(p, o, at: 161).due)
}
test("dirty flag not cleared by host does not spam") {
    let p = primed(); var o = observation(); o.edited = true
    _ = decision(p, o, at: 160); p.sent(o, now: 160)
    try expect(!decision(p, o, at: 220).due)
}
test("another document needs stabilization but no full cadence restart") {
    let p = primed(); let b = observation(window: 2, document: "file:///tmp/b.ai")
    try expect(!decision(p, b, at: 160).due); try expect(decision(p, b, at: 163).due)
}
test("switching away invalidates window stability") {
    let p = primed(); _ = decision(p, SaveObservation(), at: 160)
    try expect(!decision(p, at: 200).due); try expect(decision(p, at: 203).due)
}
test("transient cancellation retries without permanent failure") {
    let p = primed(); p.cancelled(processKey: ai.key, now: 160)
    try expect(!decision(p, at: 161).due); try expect(!decision(p, at: 162).due)
    try expect(decision(p, at: 164).due)
}
test("per-app timers remain independent") {
    let p = primed(); _ = decision(p, observation(ps), at: 110)
    p.ended(processKey: ps.key)
    _ = decision(p, at: 155); try expect(decision(p, at: 160).due)
}
test("exiting application clears timer and document state") {
    let p = primed(); p.ended(processKey: ai.key)
    try expect(!decision(p, at: 160).due); try expect(decision(p, at: 220).due)
}
test("wake reset does not catch up stale requests") {
    let p = primed(); p.reset(); try expect(!decision(p, at: 2000).due)
}
test("monotonic clock reversal resets cadence") {
    let p = primed(); _ = decision(p, at: 10); try expect(!decision(p, at: 11).due)
}
test("recheck rejects foreground instance and document changes") {
    let o = observation()
    try expect(!SavePolicy.recheck(o, observation(ps)))
    try expect(!SavePolicy.recheck(o, observation(window: 2)))
    try expect(!SavePolicy.recheck(o, observation(document: "file:///tmp/b.ai")))
    let reused = ApplicationSession(id: ai.id, name: ai.name, pid: ai.pid, launch: "999")
    try expect(!SavePolicy.recheck(o, observation(reused)))
}
test("recheck rejects late input and permissions") {
    let o = observation(); var changed = o; changed.lastInputTime = 159
    try expect(!SavePolicy.recheck(o, changed)); changed = o; changed.permitted = false
    try expect(!SavePolicy.recheck(o, changed)); changed = o; changed.pressed = true
    try expect(!SavePolicy.recheck(o, changed)); changed = o; changed.blocked = "dialog"
    try expect(!SavePolicy.recheck(o, changed))
}
test("recheck accepts cosmetic title change") {
    try expect(SavePolicy.recheck(observation(), observation(title: "a.ai *")))
}
test("session starts pending; declining is not asked repeatedly") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: [ai.id])
    try expect(r.nextPending == ai); r.decide(ai, approved: false)
    r.reconcile(running: [ai], selected: [ai.id])
    try expect(r.nextPending == nil && r.approvedCount == 0)
}
test("multiple sessions queue and remain independent") {
    let r = SessionRegistry(); r.reconcile(running: [ai, ps], selected: [ai.id, ps.id])
    r.decide(ai, approved: true); try expect(r.nextPending == ps && r.approvedKeys == [ai.key])
    r.decide(ps, approved: false); try expect(r.approvedKeys == [ai.key])
}
test("exited instance cannot accept a late response") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: [ai.id])
    r.reconcile(running: [], selected: [ai.id]); r.decide(ai, approved: true)
    try expect(r.approvedCount == 0)
}
test("PID reuse requires a new confirmation") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: [ai.id]); r.decide(ai, approved: true)
    let next = ApplicationSession(id: ai.id, name: ai.name, pid: ai.pid, launch: "101")
    let ended = r.reconcile(running: [next], selected: [ai.id])
    r.decide(ai, approved: true)
    try expect(ended == [ai.key] && r.nextPending == next && r.approvedCount == 0)
}
test("deselect and reselect require new confirmation") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: [ai.id]); r.decide(ai, approved: true)
    r.reconcile(running: [ai], selected: []); r.reconcile(running: [ai], selected: [ai.id])
    try expect(r.nextPending == ai && r.approvedCount == 0)
}
test("fresh helper never restores prior consent") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: [ai.id]); r.decide(ai, approved: true)
    let next = SessionRegistry(); next.reconcile(running: [ai], selected: [ai.id]); try expect(next.approvedCount == 0)
}
test("manual reconfirmation returns declined session to pending") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: [ai.id]); r.decide(ai, approved: false)
    r.requestAgain(ai); try expect(r.nextPending == ai)
}
test("duplicate lifecycle signals do not duplicate prompt") {
    let r = SessionRegistry(); r.reconcile(running: [ai, ai], selected: [ai.id]); r.decide(ai, approved: true)
    r.reconcile(running: [ai, ai], selected: [ai.id]); try expect(r.sessions.count == 1 && r.nextPending == nil)
}
test("settings choice does not imply consent") {
    let r = SessionRegistry(); r.reconcile(running: [ai], selected: Set(SaveSettings().applications))
    try expect(r.approvedCount == 0)
}
test("discovery search dedupes and excludes self") {
    let apps = [
        DiscoveredApplication(id: ai.id, name: ai.name, path: "/a", session: ai),
        DiscoveredApplication(id: ai.id, name: ai.name, path: "/b", session: ai),
        DiscoveredApplication(id: Product.bundleID, name: "Self", path: "/c", session: nil),
        DiscoveredApplication(id: ps.id, name: ps.name, path: "/d", session: ps)
    ]
    try expect(ApplicationDiscovery.candidates(apps).count == 2)
    try expect(ApplicationDiscovery.candidates(apps, query: "PHOTOSHOP").map(\.id) == [ps.id])
    try expect(ApplicationDiscovery.candidates(apps, query: "missing").isEmpty)
}
test("manual bundle validates metadata") {
    let bundle = temp.appendingPathComponent("Example.app")
    try FileManager.default.createDirectory(at: bundle.appendingPathComponent("Contents"), withIntermediateDirectories: true)
    let plist: [String: Any] = ["CFBundleIdentifier": "test.example", "CFBundleName": "示例", "CFBundlePackageType": "APPL"]
    try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0).write(to: bundle.appendingPathComponent("Contents/Info.plist"))
    let app = try ApplicationDiscovery.fromBundle(bundle)
    try expect(app.id == "test.example" && app.name == "示例")
}
test("non-app bundle is rejected") {
    do { _ = try ApplicationDiscovery.fromBundle(temp); throw Failure(description: "accepted directory") }
    catch is DiscoveryError {}
}
test("first-save heuristics and local paths") {
    try expect(DocumentRules.firstSave(title: "未命名-1"))
    try expect(DocumentRules.firstSave(title: "Untitled-2"))
    try expect(!DocumentRules.firstSave(title: "Poster.ai"))
    try expect(DocumentRules.localDocument("cloud://doc") == nil)
    try expect(DocumentRules.localDocument("") == nil)
    try expect(DocumentRules.localDocument("file:///tmp/a%20b.ai")?.path == "/tmp/a b.ai")
}
for mask in 0..<8 {
    test("permission combination \(mask) preserves discovery isolation") {
        let p = SavePermissions(accessibility: mask & 1 != 0, listening: mask & 2 != 0, posting: mask & 4 != 0)
        try expect(p.ready == (mask == 7))
        // Never pretend the local process has permissions. Only blocked branches
        // execute native calls; full authorization is represented in policy tests.
        if !p.ready {
            let backend = MacSaveBackend(permissionProvider: { p })
            let o = backend.observe(session: ai, permissions: p)
            try expect(!o.permitted && backend.protectedObservations == 0 && backend.sendCount == 0)
            _ = backend.sendSave(expected: observation(), stillAuthorized: { true })
            try expect(backend.protectedObservations == 0 && backend.sendCount == 0)
        }
        _ = ApplicationDiscovery.running()
    }
}
test("revoked dispatch ticket cancels before protected reads") {
    let backend = MacSaveBackend()
    _ = backend.sendSave(expected: observation(), stillAuthorized: { false })
    try expect(backend.protectedObservations == 0 && backend.sendCount == 0)
}
test("generation gate invalidates in-flight callbacks") {
    let gate = DispatchGate(); let a = gate.ticket(); try expect(gate.valid(a))
    gate.invalidate(); try expect(!gate.valid(a)); try expect(gate.valid(gate.ticket()))
}

test("pointer movement delays but does not create new save work") {
    let p = primed(); var o = observation(); o.activityToken = 5
    _ = decision(p, o, at: 160); p.sent(o, now: 160)
    o.lastInputTime = 219; o.idle = 1
    try expect(!decision(p, o, at: 220).due)
    o.idle = 10
    try expect(!decision(p, o, at: 230).due)
    o.activityToken = 6; o.lastInputTime = 230
    try expect(decision(p, o, at: 240).due)
}
for seconds in [3, 5, 10] {
    test("configurable idle threshold \(seconds)") {
        var settings = SaveSettings(); settings.idleSeconds = seconds
        let p = primed(); var o = observation(); o.idle = Double(seconds) - 0.01
        try expect(!decision(p, o, at: 160, settings: settings).due)
        o.idle = Double(seconds)
        try expect(decision(p, o, at: 161, settings: settings).due)
    }
}
test("window must stay stable for a full idle period") {
    let p = primed(); p.invalidateForeground()
    try expect(!decision(p, at: 200).due); try expect(!decision(p, at: 202.99).due)
    try expect(decision(p, at: 203).due)
}
test("recheck applies selected idle threshold and event token") {
    var o = observation(); o.activityToken = 1; var next = o; next.idle = 4
    try expect(!SavePolicy.recheck(o, next, idleRequired: 5))
    next.idle = 10; next.activityToken = 2
    try expect(!SavePolicy.recheck(o, next, idleRequired: 5))
}
test("final hardware snapshot detects quick released input") {
    var o = observation(); o.activityToken = 1
    let input = HardwareInput(idle: 0.1, lastInputTime: 159.9, pressed: false, activityToken: 2)
    try expect(!input.unchanged(from: o, idleRequired: 3))
}
test("no event bursts after a long busy period") {
    let p = primed(); var o = observation(); o.pressed = true; o.idle = 999
    for time in stride(from: 160.0, through: 1000, by: 60) { try expect(!decision(p, o, at: time).due) }
    o.pressed = false
    try expect(decision(p, o, at: 1001).due); p.sent(o, now: 1001)
    try expect(!decision(p, o, at: 1002).due)
}
test("rescue preserves full tree and verifies hashes without modifying source") {
    let source = temp.appendingPathComponent("DataRecovery")
    try FileManager.default.createDirectory(at: source.appendingPathComponent("1/Sentinel/IPCStream"), withIntermediateDirectories: true)
    let data = Data("recovery fixture, not an Illustrator document".utf8)
    let file = source.appendingPathComponent("1/Sentinel/IPCStream/IPCStream_0.aishm")
    try data.write(to: file)
    try Data([1,2,3]).write(to: source.appendingPathComponent("Metadata.aishm"))
    let service = RecoveryService(storage: temp.appendingPathComponent("vault"))
    let snapshot = try service.capture(applicationID: ai.id, name: ai.name,
        sources: [RecoverySource(name: "fixture", url: source)], reason: "test")
    try expect(snapshot.manifest.consistency == "verified" && snapshot.manifest.files.count == 2)
    try expect(snapshot.manifest.files.map(\.stored) == ["source-01/1/Sentinel/IPCStream/IPCStream_0.aishm", "source-01/Metadata.aishm"], "stored paths: \(snapshot.manifest.files.map(\.stored)), sources: \(snapshot.manifest.files.map(\.source))")
    let saved = try Data(contentsOf: snapshot.directory.appendingPathComponent("source-01/1/Sentinel/IPCStream/IPCStream_0.aishm"))
    let original = try Data(contentsOf: file)
    try expect(saved == data && original == data && snapshot.manifest.output == nil)
    try expect(snapshot.manifest.stage == "快照副本校验通过")
    try expect(service.snapshots().count == 1)
}
test("empty recovery directory never claims success") {
    let source = temp.appendingPathComponent("empty")
    try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    do {
        _ = try RecoveryService(storage: temp.appendingPathComponent("empty-vault")).capture(
            applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: source)], reason: "test")
        throw Failure(description: "empty accepted")
    } catch RecoveryFailure.noData {}
}
test("recovery copies communication file without pretending it is a drawing") {
    let file = temp.appendingPathComponent("shared-memory")
    try Data(repeating: 0, count: 65536).write(to: file)
    let service = RecoveryService(storage: temp.appendingPathComponent("communication-vault"))
    let snapshot = try service.capture(applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: file)], reason: "test")
    try expect(snapshot.manifest.output == nil && !snapshot.manifest.stage.contains("内容已确认"))
}
test("recovery refuses recursive destination") {
    let source = temp.appendingPathComponent("recursive")
    try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    try Data([1]).write(to: source.appendingPathComponent("x"))
    do {
        _ = try RecoveryService(storage: source.appendingPathComponent("vault")).capture(applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: source)], reason: "test")
        throw Failure(description: "recursive accepted")
    } catch RecoveryFailure.invalid {}
}
test("recovery skips symlinks and records incomplete status") {
    let source = temp.appendingPathComponent("links")
    try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    try Data([1]).write(to: source.appendingPathComponent("real"))
    try FileManager.default.createSymbolicLink(at: source.appendingPathComponent("external"), withDestinationURL: temp.appendingPathComponent("settings.json"))
    let snapshot = try RecoveryService(storage: temp.appendingPathComponent("links-vault")).capture(
        applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: source)], reason: "test")
    try expect(snapshot.manifest.files.count == 1 && snapshot.manifest.consistency == "needs_review")
}
test("recovery byte limits retain originals") {
    let file = temp.appendingPathComponent("large"); try Data(repeating: 1, count: 100).write(to: file)
    do {
        _ = try RecoveryService(storage: temp.appendingPathComponent("limited-vault"), byteLimit: 50).capture(
            applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: file)], reason: "test")
        throw Failure(description: "limit ignored")
    } catch RecoveryFailure.limit {}
    let data = try Data(contentsOf: file); try expect(data.count == 100)
}
test("recovery output requires separate file and explicit content confirmation") {
    let source = temp.appendingPathComponent("original.ai"); try Data("original".utf8).write(to: source)
    let service = RecoveryService(storage: temp.appendingPathComponent("output-vault"))
    let snapshot = try service.capture(applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: source)], reason: "test")
    do { _ = try service.recordOutput(source, snapshot: snapshot); throw Failure(description: "original accepted") }
    catch RecoveryFailure.invalid {}
    let output = temp.appendingPathComponent("recovered.ai"); try Data("new fixture content".utf8).write(to: output)
    let recorded = try service.recordOutput(output, snapshot: snapshot)
    try expect(recorded.manifest.output?.contentConfirmed == false)
    let confirmed = try service.confirmContent(recorded)
    try expect(confirmed.manifest.stage == "内容已确认")
    try Data("changed again".utf8).write(to: output)
    do { _ = try service.confirmContent(recorded); throw Failure(description: "changed output accepted") }
    catch RecoveryFailure.invalid {}
}
test("recovery discovery recognizes locale trees and Photoshop AutoRecover") {
    let home = temp.appendingPathComponent("home")
    let aiRoot = home.appendingPathComponent("Library/Preferences/Adobe Illustrator 30 Settings/zh_TW/DataRecovery")
    let psRoot = home.appendingPathComponent("Library/Application Support/Adobe/Adobe Photoshop 2026/AutoRecover")
    try FileManager.default.createDirectory(at: aiRoot, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: psRoot, withIntermediateDirectories: true)
    let foundAI = RecoveryDiscovery.sources(for: ai.id, home: home).map { $0.url.resolvingSymlinksInPath().path }
    let foundPS = RecoveryDiscovery.sources(for: ps.id, home: home).map { $0.url.resolvingSymlinksInPath().path }
    try expect(foundAI == [aiRoot.resolvingSymlinksInPath().path], "unexpected AI paths: \(foundAI)")
    try expect(foundPS == [psRoot.resolvingSymlinksInPath().path], "unexpected PS paths: \(foundPS)")
    try expect(RecoveryDiscovery.sources(for: "unsupported", home: home).isEmpty)
}

test("active source mutation is reported, never marked fully verified") {
    let source = temp.appendingPathComponent("active.aishm"); try Data("before".utf8).write(to: source)
    let service = RecoveryService(storage: temp.appendingPathComponent("active-vault"))
    let snapshot = try service.capture(applicationID: ai.id, name: ai.name,
        sources: [RecoverySource(name: "", url: source)], reason: "test", progress: { _, _ in
            try! Data("after changed".utf8).write(to: source)
        })
    try expect(snapshot.manifest.consistency == "needs_review" && !snapshot.manifest.warnings.isEmpty)
}
test("two snapshots preserve previous evidence") {
    let source = temp.appendingPathComponent("versions.aishm"); try Data("one".utf8).write(to: source)
    let service = RecoveryService(storage: temp.appendingPathComponent("versions-vault"))
    let first = try service.capture(applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: source)], reason: "first")
    try Data("two".utf8).write(to: source)
    let second = try service.capture(applicationID: ai.id, name: ai.name, sources: [RecoverySource(name: "", url: source)], reason: "second")
    try expect(first.directory != second.directory && service.snapshots().count == 2)
    try expect(first.manifest.files.first?.sha256 != second.manifest.files.first?.sha256)
}
test("system temporary directory comes from macOS and exists") {
    let detected = RecoveryDiscovery.systemTemporaryDirectory()
    let system = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true).standardizedFileURL.resolvingSymlinksInPath()
    var directory: ObjCBool = false
    try expect(detected.isFileURL && detected.path == system.path)
    try expect(FileManager.default.fileExists(atPath: detected.path, isDirectory: &directory) && directory.boolValue)
}
test("partial snapshot files count toward vault capacity") {
    let vault = temp.appendingPathComponent("partial-vault")
    try FileManager.default.createDirectory(at: vault, withIntermediateDirectories: true)
    try Data(repeating: 1, count: 80).write(to: vault.appendingPathComponent("partial.bin"))
    let source = temp.appendingPathComponent("bounded.aishm"); try Data(repeating: 2, count: 40).write(to: source)
    do {
        _ = try RecoveryService(storage: vault, vaultLimit: 100).capture(applicationID: ai.id, name: ai.name,
            sources: [RecoverySource(name: "", url: source)], reason: "test")
        throw Failure(description: "unrecorded partial data ignored")
    } catch RecoveryFailure.limit {}
    let original = try Data(contentsOf: source); try expect(original.count == 40)
}
test("permission revocation between scheduling and observation performs no protected query") {
    let backend = MacSaveBackend(permissionProvider: { SavePermissions(accessibility: false, listening: true, posting: false) })
    let observed = backend.observe(session: ai, permissions: SavePermissions(accessibility: true, listening: true, posting: true))
    try expect(!observed.permitted && backend.protectedObservations == 0 && backend.sendCount == 0)
}
print("RESULT \(passed) passed; \(failed) failed. No save events were posted.")
exit(failed == 0 ? 0 : 1)
