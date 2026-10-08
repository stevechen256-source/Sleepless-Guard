import Foundation

@main
enum PowerStateTests {
    static func main() throws {
        var count = 0
        func check(_ condition: Bool, _ message: String) {
            count += 1
            if !condition { fatalError("FAILED: " + message) }
        }
        for (code, text, expected) in [
            (0, "SleepDisabled 0\n", PowerFlag.off), (0, " SleepDisabled 1\n", .on),
            (1, "SleepDisabled 0\n", .unknown), (0, "", .unknown),
            (0, "sleep 1", .unknown), (0, "SleepDisabled 7", .unknown),
            (0, "SleepDisabled 0\nSleepDisabled 1", .unknown),
            (0, "SleepDisabled 0 junk", .unknown), (-2, "", .unknown)
        ] {
            check(PowerObservation.parse(.init(exitCode: code, output: text, error: ""), now: 100).state == expected, "three-state parser")
        }
        let off = PowerObservation(state: .off, exit_code: 0, error: nil, sampled_at: 100)
        let on = PowerObservation(state: .on, exit_code: 0, error: nil, sampled_at: 100)
        check(verifiedRequest(.init(exitCode: 0, output: "", error: ""), observation: off, wanted: .off), "verified off")
        check(!verifiedRequest(.init(exitCode: 1, output: "", error: "denied"), observation: off, wanted: .off), "denial is not success")
        check(!verifiedRequest(.init(exitCode: 0, output: "", error: ""), observation: on, wanted: .off), "unchanged flag is not success")

        let sample: [String: Any] = ["state": "off", "exit_code": 0, "error": NSNull(), "sampled_at": 100.0]
        let reset: [String: Any] = ["requested_at": 99.0, "exit_code": 0, "error": NSNull(),
            "verified": true, "observation": sample, "attempts": 1]
        let base: [String: Any] = ["schema_version": 2, "version": guardProtocolVersion,
            "updated": 100.0, "pid": 777, "uid": 501, "launch_agent": "io.github.sleeplesscn.guard",
            "executable": "/usr/bin/python3", "script_path": "/test/guard.py", "observation": sample,
            "source": "battery", "battery_percent": 50, "app_running": true, "app_responsive": true,
            "health": "healthy", "reason": "normal", "remaining_seconds": NSNull(), "last_reset": reset]
        func evaluate(_ object: [String: Any], pid: Int? = 777, uid: Int? = 501,
                      args: String? = "/usr/bin/python3 /test/guard.py") throws -> GuardAssessment {
            GuardAssessment.evaluate(data: try JSONSerialization.data(withJSONObject: object), now: 100,
                uid: 501, script: "/test/guard.py", launchPID: pid, processUID: uid, processArguments: args)
        }
        check(try evaluate(base).healthy, "valid report")
        for (key, value) in [("schema_version", 1 as Any), ("version", "old"), ("updated", 50.0),
                             ("updated", 102.0), ("pid", 1), ("uid", 502), ("health", "fault"),
                             ("health", "conflict"), ("app_running", false), ("app_responsive", false),
                             ("source", "unknown"), ("battery_percent", -1), ("remaining_seconds", -1),
                             ("remaining_seconds", 43201), ("script_path", "/other/guard.py"),
                             ("launch_agent", "other.agent")] {
            var report = base; report[key] = value
            check(try !evaluate(report).healthy, "reject " + key)
        }
        for (key, value) in [("state", "unknown" as Any), ("state", "broken"), ("exit_code", 1),
                             ("error", "read_failed"), ("sampled_at", 50.0)] {
            var obs = sample; obs[key] = value
            var report = base; report["observation"] = obs
            check(try !evaluate(report).healthy, "reject invalid observation " + key)
        }
        for (key, value) in [("verified", false as Any), ("exit_code", 1), ("attempts", 0), ("attempts", 3),
                             ("observation", ["state": "on", "exit_code": 0, "sampled_at": 99.0])] {
            var failed = reset; failed[key] = value
            var report = base; report["last_reset"] = failed
            check(try !evaluate(report).healthy, "reject reset " + key)
        }
        check(try !evaluate(base, pid: nil).healthy, "missing launch agent")
        check(try !evaluate(base, pid: 778).healthy, "PID reuse or stale report")
        check(try !evaluate(base, uid: 502).healthy, "foreign process UID")
        check(try !evaluate(base, args: "/usr/bin/python3 /other/guard.py").healthy, "wrong script with same PID")
        check(try !evaluate(base, args: "/bin/echo /test/guard.py").healthy, "wrong executable")
        check(!GuardAssessment.evaluate(data: Data("{broken".utf8), now: 100, uid: 501, script: "/test/guard.py",
            launchPID: 777, processUID: 501, processArguments: "").healthy, "truncated JSON")

        // Only harmless subprocess fixtures; no pmset, sudo, launchctl, or app installation.
        let fixture = BoundedCommand.run("/bin/sh", ["-c", "printf 'ok'; printf 'detail' >&2; exit 7"])
        check(fixture.exitCode == 7 && fixture.output == "ok" && fixture.error == "detail", "captures exit and both outputs")
        check(BoundedCommand.run("/bin/sh", ["-c", "exec /bin/sleep 2"], timeout: 0.05).exitCode == -2, "bounded timeout")
        check(BoundedCommand.run("/no/such/fixture", []).exitCode == -1, "launch failure")
        print("PASS \(count) Swift state, heartbeat identity, and bounded-command checks; no power commands executed")
    }
}
