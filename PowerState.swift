import Foundation
import Darwin

let guardProtocolVersion = "0.2.0-dev"

enum PowerFlag: String, Codable { case on, off, unknown }

struct CommandResult {
    let exitCode: Int
    let output: String
    let error: String
}

struct PowerObservation: Codable {
    let state: PowerFlag
    let exit_code: Int
    let error: String?
    let sampled_at: Double

    static func parse(_ result: CommandResult, now: Double) -> PowerObservation {
        guard result.exitCode == 0 else {
            return .init(state: .unknown, exit_code: result.exitCode, error: "read_failed", sampled_at: now)
        }
        let lines = result.output.split(separator: "\n").map { $0.split(whereSeparator: { $0.isWhitespace }).map(String.init) }
        let flags = lines.filter { $0.first?.lowercased() == "sleepdisabled" }
        guard flags.count == 1, flags[0].count == 2, ["0", "1"].contains(flags[0][1]) else {
            return .init(state: .unknown, exit_code: 0, error: "unparseable_flag", sampled_at: now)
        }
        return .init(state: flags[0][1] == "1" ? .on : .off, exit_code: 0, error: nil, sampled_at: now)
    }

    func fresh(at now: Double, maximumAge: Double = 30) -> Bool {
        sampled_at.isFinite && now - sampled_at >= -1 && now - sampled_at < maximumAge
    }
}

struct ResetReport: Decodable {
    let requested_at: Double
    let exit_code: Int
    let error: String?
    let verified: Bool
    let observation: PowerObservation
    let attempts: Int
}

struct GuardReport: Decodable {
    let schema_version: Int
    let version: String
    let updated: Double
    let pid: Int
    let uid: Int
    let launch_agent: String
    let executable: String
    let script_path: String
    let observation: PowerObservation
    let source: String
    let battery_percent: Int
    let app_running: Bool
    let app_responsive: Bool
    let health: String
    let reason: String
    let remaining_seconds: Double?
    let last_reset: ResetReport?
}

struct GuardAssessment {
    let report: GuardReport?
    let fault: String?
    var healthy: Bool { fault == nil && report != nil }

    static func evaluate(data: Data?, now: Double, uid: Int, script: String,
                         launchPID: Int?, processUID: Int?, processArguments: String?) -> GuardAssessment {
        guard let data, data.count < 65536,
              let s = try? JSONDecoder().decode(GuardReport.self, from: data) else {
            return .init(report: nil, fault: "invalid_status")
        }
        func fail(_ code: String) -> GuardAssessment { .init(report: s, fault: code) }
        guard s.schema_version == 2, s.version == guardProtocolVersion else { return fail("protocol_mismatch") }
        guard s.updated.isFinite, now - s.updated >= -1, now - s.updated < 30 else { return fail("stale_heartbeat") }
        guard s.uid == uid, s.pid > 1, s.pid == launchPID, processUID == uid,
              s.launch_agent == "io.github.sleeplesscn.guard", s.script_path == script,
              s.executable.hasPrefix("/"), let args = processArguments else { return fail("identity_mismatch") }
        // ps may display the interpreter through its launch path or resolved path.
        let suffix = " " + script
        guard args.hasSuffix(suffix) else { return fail("identity_mismatch") }
        let interpreter = String(args.dropLast(suffix.count))
        let resolved = URL(fileURLWithPath: interpreter).resolvingSymlinksInPath().path
        let expected = URL(fileURLWithPath: s.executable).resolvingSymlinksInPath().path
        guard [s.executable, "/usr/bin/python3"].contains(interpreter) || resolved == expected else {
            return fail("identity_mismatch")
        }
        if let reset = s.last_reset {
            guard reset.verified, reset.exit_code == 0, reset.error == nil, reset.observation.state == .off,
                  reset.observation.exit_code == 0, reset.observation.error == nil,
                  reset.attempts >= 1, reset.attempts <= 2 else { return fail("reset_failed") }
        }
        guard s.health == "healthy" else { return fail(s.health == "conflict" ? "controller_conflict" : "guard_fault") }
        guard s.app_running, s.app_responsive else { return fail("app_unresponsive") }
        guard s.observation.state != .unknown, s.observation.exit_code == 0,
              s.observation.error == nil, s.observation.fresh(at: now),
              ["ac", "battery"].contains(s.source), (0...100).contains(s.battery_percent) else {
            return fail("unknown_observation")
        }
        if let remaining = s.remaining_seconds, !remaining.isFinite || remaining < 0 || remaining > 43200 {
            return fail("invalid_status")
        }
        return .init(report: s, fault: nil)
    }
}

func verifiedRequest(_ result: CommandResult, observation: PowerObservation, wanted: PowerFlag) -> Bool {
    result.exitCode == 0 && observation.exit_code == 0 && observation.error == nil && observation.state == wanted
}

// Separate stdout/stderr files avoid pipe-buffer deadlocks. Timeouts affect only
// the subprocess created by this call; no unrelated application is signalled.
enum BoundedCommand {
    static func run(_ path: String, _ arguments: [String], timeout: TimeInterval = 4) -> CommandResult {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("SleeplessGuard-" + UUID().uuidString)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: false,
                                                    attributes: [.posixPermissions: 0o700])
            defer { try? FileManager.default.removeItem(at: dir) }
            let out = dir.appendingPathComponent("stdout"), err = dir.appendingPathComponent("stderr")
            FileManager.default.createFile(atPath: out.path, contents: nil, attributes: [.posixPermissions: 0o600])
            FileManager.default.createFile(atPath: err.path, contents: nil, attributes: [.posixPermissions: 0o600])
            let stdout = try FileHandle(forWritingTo: out), stderr = try FileHandle(forWritingTo: err)
            defer { try? stdout.close(); try? stderr.close() }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: path)
            process.arguments = arguments
            var environment = ProcessInfo.processInfo.environment
            environment["LC_ALL"] = "C"
            process.environment = environment
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = stdout
            process.standardError = stderr
            try process.run()
            let deadline = ProcessInfo.processInfo.systemUptime + timeout
            while process.isRunning && ProcessInfo.processInfo.systemUptime < deadline { Thread.sleep(forTimeInterval: 0.01) }
            if process.isRunning {
                process.terminate()
                let grace = ProcessInfo.processInfo.systemUptime + 0.2
                while process.isRunning && ProcessInfo.processInfo.systemUptime < grace { Thread.sleep(forTimeInterval: 0.01) }
                if process.isRunning { kill(process.processIdentifier, SIGKILL) }
                return .init(exitCode: -2, output: "", error: "command_timeout")
            }
            func limited(_ url: URL) -> String {
                guard let handle = try? FileHandle(forReadingFrom: url) else { return "" }
                defer { try? handle.close() }
                return String(data: (try? handle.read(upToCount: 65536)) ?? Data(), encoding: .utf8) ?? ""
            }
            return .init(exitCode: Int(process.terminationStatus), output: limited(out), error: limited(err))
        } catch {
            return .init(exitCode: -1, output: "", error: "command_launch_failed")
        }
    }
}
