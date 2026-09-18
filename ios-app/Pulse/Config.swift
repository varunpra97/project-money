import Foundation

/// Single place for app configuration.
enum AppConfig {
    /// Your Pulse API's public URL, e.g. "https://abc123.trycloudflare.com".
    /// No trailing slash. Leave empty to see the in-app setup screen.
    ///
    /// NOTE: tunnel URLs (trycloudflare.com) change when the backend restarts —
    /// if the app suddenly can't reach the API, paste the fresh URL here and rebuild.
    /// The API is served under the /pulse path on the public host.
    static let baseURL = "https://guided-appears-surname-yang.trycloudflare.com/pulse"
}
