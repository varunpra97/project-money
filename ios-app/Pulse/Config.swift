import Foundation

struct AppConfig {
    // Hosted backend on Render (always on). Tailscale address kept as fallback.
    // Override PULSE_BACKEND_URL in the Xcode scheme for a different server.
    static let baseURL = ProcessInfo.processInfo.environment["PULSE_BACKEND_URL"]
        ?? "https://pulse-backend-jiar.onrender.com/pulse"
}
