import Foundation

enum APIError: LocalizedError {
    case server(String)
    case notConfigured
    case badURL(String)
    case http(Int)
    case decoding(Error)
    case network(Error)

    var errorDescription: String? {
        switch self {
        case .server(let message):
            return message
        case .notConfigured:
            return "Set AppConfig.baseURL to your API's public URL, then rebuild."
        case .badURL(let path):
            return "Bad URL for \(path)."
        case .http(let code):
            return "Server returned HTTP \(code)."
        case .decoding:
            return "Couldn't read the server's response."
        case .network(let err):
            return "Check that Tailscale is connected and the Windows server is awake. " + err.localizedDescription
        }
    }
}

enum QuoteRange: String, CaseIterable, Identifiable {
    case oneDay = "1d"
    case fiveDay = "5d"
    case oneMonth = "1mo"
    case threeMonth = "3mo"
    case oneYear = "1y"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .oneDay: return "1D"
        case .fiveDay: return "1W"
        case .oneMonth: return "1M"
        case .threeMonth: return "3M"
        case .oneYear: return "1Y"
        }
    }
}

/// The Windows server owns freshness and shared provider caching.
/// Every client call reaches the server; views may retain dated display state.
/// Thread-safe: safe to call from any task or actor.
final class APIClient {
    static let shared = APIClient()

    private let session: URLSession

    init(configuration: URLSessionConfiguration = .default) {
        let cfg = configuration
        cfg.urlCache = nil
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        cfg.timeoutIntervalForRequest = 35
        self.session = URLSession(configuration: cfg)
    }

    func invalidateCache() {
        // Compatibility for existing pull-to-refresh callers; no client cache.
    }

    private func url(for path: String, query: [String: String] = [:]) throws -> URL {
        guard !AppConfig.baseURL.isEmpty else { throw APIError.notConfigured }
        var base = AppConfig.baseURL
        if base.hasSuffix("/") { base.removeLast() }
        let clean = path.hasPrefix("/") ? String(path.dropFirst()) : path
        var comps = URLComponents(string: base + "/" + clean)
        if !query.isEmpty {
            comps?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let u = comps?.url else { throw APIError.badURL(path) }
        return u
    }

    func get<T: Decodable>(
        _ path: String,
        query: [String: String] = [:],
        ttl: TimeInterval = 60 // Retained for existing callers; server owns TTLs.
    ) async throws -> T {
        let u = try url(for: path, query: query)
        do {
            let (data, resp) = try await session.data(from: u)
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let message = (payload["error"] ?? payload["detail"]) as? String { throw APIError.server(message) }
            guard let http = resp as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode)
            else {
                throw APIError.http((resp as? HTTPURLResponse)?.statusCode ?? -1)
            }
            let decoded: T = try decode(data)
            return decoded
        } catch let apiErr as APIError {
            throw apiErr
        } catch {
            throw APIError.network(error)
        }
    }

    private func decode<T: Decodable>(_ data: Data) throws -> T {
        // Fresh decoder per call: JSONDecoder is not thread-safe.
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    func post<T: Decodable>(_ path: String, body: [String: Any] = [:]) async throws -> T {
        let u = try url(for: path)
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        do {
            let (data, resp) = try await session.data(for: req)
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let message = (payload["error"] ?? payload["detail"]) as? String {
                throw APIError.server(message)
            }
            guard let http = resp as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode)
            else {
                throw APIError.http((resp as? HTTPURLResponse)?.statusCode ?? -1)
            }
            return try decode(data)
        } catch let apiErr as APIError {
            throw apiErr
        } catch {
            throw APIError.network(error)
        }
    }

    // MARK: - Endpoints

    /// Read-only token for the real-brokerage endpoints, injected at build
    /// time via $(APP_READ_TOKEN) in Info.plist. Nil when the build didn't
    /// provide one — brokerage endpoints then stay unreachable.
    private var appReadToken: String? {
        guard let t = Bundle.main.object(forInfoDictionaryKey: "AppReadToken") as? String,
              !t.isEmpty, !t.contains("$(") else { return nil }
        return t
    }

    private func authedRequest(for url: URL) -> URLRequest {
        var req = URLRequest(url: url)
        if let tok = appReadToken {
            req.setValue(tok, forHTTPHeaderField: "X-App-Token")
        }
        return req
    }

    private func check(_ data: Data, _ resp: URLResponse) throws -> Data {
        if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let message = (payload["error"] ?? payload["detail"]) as? String {
            throw APIError.server(message)
        }
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError.http((resp as? HTTPURLResponse)?.statusCode ?? -1)
        }
        return data
    }

    func authedGet<T: Decodable>(_ path: String, ttl: TimeInterval = 60) async throws -> T {
        let u = try url(for: path)
        do {
            let (data, resp) = try await session.data(for: authedRequest(for: u))
            return try decode(check(data, resp))
        } catch let apiErr as APIError {
            throw apiErr
        } catch {
            throw APIError.network(error)
        }
    }

    func authedPost<T: Decodable>(_ path: String, body: [String: Any] = [:]) async throws -> T {
        let u = try url(for: path)
        var req = authedRequest(for: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        do {
            let (data, resp) = try await session.data(for: req)
            return try decode(check(data, resp))
        } catch let apiErr as APIError {
            throw apiErr
        } catch {
            throw APIError.network(error)
        }
    }

    func health() async throws -> HealthResponse {
        try await get("/api/health", ttl: 30)
    }

    func summary() async throws -> PortfolioSummary {
        try await get("/api/portfolio/summary", ttl: 30)
    }

    func positions() async throws -> [Position] {
        let r: PositionsResponse = try await get("/api/portfolio/positions", ttl: 30)
        return r.positions
    }

    // MARK: - Real brokerage book (Robinhood via Plaid)

    /// Live positions from the synced brokerage snapshot. Throws
    /// APIError.http(404) when no snapshot has synced yet.
    func brokeragePositions() async throws -> [Position] {
        let r: PositionsResponse = try await authedGet("/api/brokerage/positions", ttl: 30)
        return r.positions
    }

    func brokerageSummary() async throws -> PortfolioSummary {
        try await authedGet("/api/brokerage/summary", ttl: 30)
    }

    /// Shock the real book with a price move, an IV jump, and time decay.
    func brokerageStressTest(priceMovePct: Double, volJumpPct: Double, daysForward: Int) async throws -> StressTestResponse {
        try await authedPost("/api/brokerage/stress/test", body: [
            "price_move_pct": priceMovePct,
            "vol_jump_pct": volJumpPct,
            "days_forward": daysForward,
        ])
    }

    func activity() async throws -> [ActivityItem] {
        let r: ActivityResponse = try await get("/api/portfolio/activity", ttl: 60)
        return r.activity
    }

    func celebrity() async throws -> CelebrityResponse {
        try await get("/api/insights/celebrity", ttl: 300)
    }

    func earnings() async throws -> EarningsResponse {
        try await get("/api/insights/earnings", ttl: 300)
    }

    func volatility() async throws -> VolatilityResponse {
        try await get("/api/insights/volatility", ttl: 300)
    }

    func candidates() async throws -> [Candidate] {
        let r: CandidatesResponse = try await get("/api/candidates", ttl: 300)
        return r.candidates
    }

    func scan() async throws -> ScanEnvelope {
        try await get("/api/scan", ttl: 300)
    }

    func breaches() async throws -> BreachesResponse {
        try await get("/api/breaches", ttl: 300)
    }

    /// Upcoming earnings / ex-dividend dates per symbol, plus FOMC dates.
    func events(symbols: [String]) async throws -> EventsResponse {
        try await get("/api/events", query: ["symbols": symbols.joined(separator: ",")], ttl: 0)
    }

    func quote(_ symbol: String, range: QuoteRange) async throws -> QuoteResponse {
        let ttl: TimeInterval = range == .oneDay ? 60 : 900
        return try await get(
            "/api/quote/\(symbol.uppercased())",
            query: ["range": range.rawValue],
            ttl: ttl
        )
    }

    // MARK: - Upgrade builder ("Build this upgrade")

    func requestUpgrade(idea: ProductIdea) async throws -> UpgradeJob {
        try await post("/api/upgrades/request", body: [
            "idea_id": idea.id,
            "title": idea.title,
            "detail": idea.detail,
            "measure": idea.measure,
            "effort": idea.effort,
        ])
    }

    func activeUpgrade() async throws -> UpgradeJob? {
        struct Wrapper: Decodable { let job: UpgradeJob? }
        let w: Wrapper = try await get("/api/upgrades/active", ttl: 0)
        return w.job
    }

    func requestUpgradeUndo(jobId: String) async throws -> UpgradeJob {
        try await post("/api/upgrades/\(jobId)/request-undo")
    }

    func likeIdea(ideaId: String) async throws {
        struct Ack: Decodable { let ok: Bool }
        let ack: Ack = try await post("/api/ideas/\(ideaId)/like")
        if !ack.ok { throw APIError.server("Like was not saved") }
    }

    // MARK: - Stress lab

    /// Shock the paper book with a price move, an IV jump, and time decay.
    func stressTest(priceMovePct: Double, volJumpPct: Double, daysForward: Int) async throws -> StressTestResponse {
        try await post("/api/stress/test", body: [
            "price_move_pct": priceMovePct,
            "vol_jump_pct": volJumpPct,
            "days_forward": daysForward,
        ])
    }
}
