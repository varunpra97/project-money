import Foundation

/// Single place for app configuration.
enum AppConfig {
    /// Your Pulse API's public URL, e.g. "https://abc123.trycloudflare.com".
    /// No trailing slash. Leave empty to see the in-app setup screen.
    ///
    /// NOTE: tunnel URLs (trycloudflare.com) change when the backend restarts —
    /// if the app suddenly can't reach the API, paste the fresh URL here and rebuild.
    static let baseURL = ""
}
