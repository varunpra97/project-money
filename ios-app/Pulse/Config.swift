import Foundation

struct AppConfig {
    // Debug builds use this Mac for development; release clients use the canonical backend.
    #if DEBUG
      #if targetEnvironment(simulator)
      static let baseURL = "http://127.0.0.1:8505"
      #else
      static let baseURL = "http://10.0.0.160:8505/pulse"
      #endif
    #else
    static let baseURL = "https://views-pill-radical-templates.trycloudflare.com/pulse"
    #endif
}
