import Foundation

struct AppConfig {
    // Windows backend, reachable on Wi-Fi or cellular with Tailscale connected.
    // Override PULSE_BACKEND_URL in the Xcode scheme for a different server.
    static let baseURL = ProcessInfo.processInfo.environment["PULSE_BACKEND_URL"]
        ?? "https://varunpc.tail68d841.ts.net/pulse"
}
