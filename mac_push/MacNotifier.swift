import Foundation
import UserNotifications

let args = CommandLine.arguments
func value(_ flag: String, default fallback: String = "") -> String {
    if let i = args.firstIndex(of: flag), i + 1 < args.count { return args[i + 1] }
    return fallback
}

let title = value("--title", default: "臻宝每日快讯")
let subtitle = value("--subtitle", default: "")
let body = value("--body", default: "有新的重要新闻")
let identifier = value("--id", default: UUID().uuidString)

let center = UNUserNotificationCenter.current()
let sem = DispatchSemaphore(value: 0)
var grantedResult = false

center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
    grantedResult = granted
    if let error = error {
        fputs("authorization error: \(error.localizedDescription)\n", stderr)
    }
    sem.signal()
}
sem.wait()

if !grantedResult {
    fputs("notification permission not granted\n", stderr)
    exit(2)
}

let content = UNMutableNotificationContent()
content.title = title
content.subtitle = subtitle
content.body = body
content.sound = UNNotificationSound.default

let request = UNNotificationRequest(identifier: identifier, content: content, trigger: nil)
let sem2 = DispatchSemaphore(value: 0)
var failed = false
center.add(request) { error in
    if let error = error {
        failed = true
        fputs("notification error: \(error.localizedDescription)\n", stderr)
    }
    sem2.signal()
}
sem2.wait()
exit(failed ? 1 : 0)
