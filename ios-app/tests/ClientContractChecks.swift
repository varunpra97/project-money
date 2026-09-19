import Foundation

// Run with Config.swift, Models.swift and APIClient.swift. No iOS runtime required.
private final class FixtureProtocol: URLProtocol {
    private static let lock = NSLock()
    private static var count = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock()
        Self.count += 1
        let call = Self.count
        Self.lock.unlock()
        let body: String
        let status: Int
        switch request.url!.lastPathComponent {
        case "http-error": status = 503; body = "{}"
        case "bad-json": status = 200; body = "{broken"
        default: status = 200; body = "{\"revision\":\(call)}"
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Cache-Control": "max-age=3600"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .allowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@main struct ClientContractChecks {
    struct Revision: Decodable { let revision: Int }
    static func require(_ condition: Bool, _ message: String) throws {
        if !condition { throw NSError(domain: "ClientContract", code: 1,
                                       userInfo: [NSLocalizedDescriptionKey: message]) }
    }
    static func main() async throws {
        if CommandLine.arguments.contains("--server") {
            let api = APIClient.shared
            let health = try await api.health()
            try require(health.ok, "Backend health failed")
            let summary = try await api.summary()
            let positions = try await api.positions()
            _ = try await api.activity()
            _ = try await api.celebrity()
            _ = try await api.earnings()
            _ = try await api.volatility()
            for range in QuoteRange.allCases {
                let quote = try await api.quote("AAPL", range: range)
                try require(!quote.bars.isEmpty && quote.asOf != nil, "Missing dated bars for \(range)")
                try require(quote.bars.allSatisfy { $0.o != nil && $0.h != nil && $0.l != nil && $0.v != nil }, "Missing OHLCV")
            }
            try require(summary.openPositions == positions.count, "Portfolio summary/positions differ")
            print("PASS: production Swift API client decoded Windows health, portfolio, activity, Discover and all 5 chart ranges")
            return
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FixtureProtocol.self]
        let client = APIClient(configuration: configuration)
        let first: Revision = try await client.get("/api/test", ttl: 3600)
        let second: Revision = try await client.get("/api/test", ttl: 3600)
        try require(second.revision > first.revision, "Client hid a server update behind its cache")
        do {
            let _: Revision = try await client.get("/api/http-error")
            fatalError("HTTP error was treated as success")
        } catch APIError.http(let status) { try require(status == 503, "Wrong HTTP status") }
        do {
            let _: Revision = try await client.get("/api/bad-json")
            fatalError("Invalid JSON was treated as success")
        } catch APIError.decoding { /* Distinct from network failure. */ }
        let quote = try JSONDecoder().decode(QuoteResponse.self, from: Data("""
        {"symbol":"AAPL","price":200,"chg_pct":1,"bars":[{"t":1,"c":200,"o":199,"h":201,"l":198,"v":100}],"as_of":"2026-09-18T19:59:00Z","source":"provider","cache_stale":true,"cache_age_seconds":90,"cache_warning":"Provider unavailable","fresh":false}
        """.utf8))
        try require(quote.cacheStale == true && quote.cacheAgeSeconds == 90 && quote.fresh == false && quote.cacheWarning != nil && quote.asOf != nil, "Lost freshness metadata")
        let legacy = try JSONDecoder().decode(Position.self, from: Data("""
        {"id":"test","underlying":"AAPL","strategy":"test","display_name":"Test fixture","opened_at":"2026-09-18T00:00:00Z"}
        """.utf8))
        try require(legacy.openingValue == nil && legacy.markAsOf == nil && legacy.dayPnl == nil, "Missing saved mark data must remain unknown")
        print("PASS: client bypasses cache, distinguishes HTTP/decoding failures, preserves freshness and older position contracts")
    }
}
