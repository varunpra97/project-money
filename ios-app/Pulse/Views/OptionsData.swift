import Foundation

// MARK: - ThetaHedge direct fetch (app.thetahedge.io, no login required)
//
// The ticker-list API is open: POST /api/stock-table with the JSON body the
// site's own client sends. We query per symbol and exact-match client-side.

private let thetaHedgeURL = URL(string: "https://app.thetahedge.io/api/stock-table")!

func fetchThetaHedgeRow(symbol: String) async throws -> ThetaHedgeRow? {
    // search_symbol is a SUBSTRING match (e.g. "V" matches hundreds of
    // tickers, and wheel_rank asc sorts unranked rank-0 rows first), so page
    // through and exact-match client-side — rows.first is the wrong ticker.
    // Page size stays at 50: the API returns [] for limit_val >= 75.
    let sym = symbol.uppercased()
    var offset = 0
    for _ in 0..<10 {
        let body: [String: Any] = [
            "limit_val": 50,
            "offset_val": offset,
            "sort_column": "wheel_rank",
            "sort_order": "asc",
            "search_symbol": sym,
            "condition_strings": [],
            "symbols": NSNull(),
            "is_heartbeat": false,
        ]
        var req = URLRequest(url: thetaHedgeURL)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("Pulse-iOS/1.0", forHTTPHeaderField: "User-Agent")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        req.timeoutInterval = 25
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        let rows = try JSONDecoder().decode([ThetaHedgeRow].self, from: data)
        if let exact = rows.first(where: { $0.symbol?.uppercased() == sym }) {
            return exact
        }
        guard rows.count == 50 else { return nil }  // ran out of matches
        offset += 50
    }
    return nil
}

// MARK: - Options chain via the Pulse backend proxy
//
// GET {baseURL}/api/options/{SYMBOL}?dte=14
//
// The app used to hit Yahoo's options API directly, but Yahoo now requires
// crumb auth (401 without it). The backend proxies via yfinance and returns
// the 3 expirations nearest the requested DTE, strikes trimmed to ±30% of
// spot. Cached server-side for 120s.

// Contract shape shared by the UI; the backend proxy's fields are mapped into it.
struct YahooOptionContract: Decodable {
    let strike: Double
    let lastPrice: Double?
    let bid: Double?
    let ask: Double?
    let volume: Int?
    let openInterest: Int?
    let impliedVolatility: Double?

    var mid: Double? {
        if let bid, let ask, bid > 0, ask > 0 { return (bid + ask) / 2 }
        return lastPrice
    }
}

struct BackendOptionContract: Decodable {
    let strike: Double
    let bid: Double?
    let ask: Double?
    let last: Double?
    let iv: Double?
    let vol: Double?
    let oi: Double?

    var asYahoo: YahooOptionContract {
        YahooOptionContract(strike: strike, lastPrice: last, bid: bid, ask: ask,
                            volume: vol.map { Int($0) },
                            openInterest: oi.map { Int($0) },
                            impliedVolatility: iv)
    }
}

struct BackendExpiry: Decodable {
    let date: String   // "YYYY-MM-DD"
    let dte: Int
    let calls: [BackendOptionContract]
    let puts: [BackendOptionContract]
}

struct BackendOptionsResponse: Decodable {
    let symbol: String?
    let underlyingPrice: Double?
    let expirations: [BackendExpiry]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case symbol, expirations, error
        case underlyingPrice = "underlying_price"
    }
}

struct ChainExpiry {
    let date: TimeInterval   // unix seconds
    let dte: Int
    let calls: [YahooOptionContract]
    let puts: [YahooOptionContract]
}

private let backendISODate: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd"
    f.timeZone = TimeZone(secondsFromGMT: 0)
    return f
}()

func fetchOptionsChain(symbol: String, dte: Int = 14) async throws -> (spot: Double?, expiries: [ChainExpiry]) {
    let sym = symbol.uppercased().addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? symbol.uppercased()
    guard let url = URL(string: "\(AppConfig.baseURL)/api/options/\(sym)?dte=\(dte)") else {
        throw APIError.badURL("api/options/\(sym)")
    }
    var req = URLRequest(url: url)
    req.setValue("application/json", forHTTPHeaderField: "Accept")
    req.timeoutInterval = 30
    let (data, resp) = try await URLSession.shared.data(for: req)
    guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
        throw APIError.http((resp as? HTTPURLResponse)?.statusCode ?? -1)
    }
    let decoded = try JSONDecoder().decode(BackendOptionsResponse.self, from: data)
    if let err = decoded.error {
        throw APIError.server(err)
    }
    guard let exps = decoded.expirations, !exps.isEmpty else {
        throw APIError.server("No options data for \(sym)")
    }
    let now = Date().timeIntervalSince1970
    let out: [ChainExpiry] = exps.compactMap { e in
        guard let dt = backendISODate.date(from: e.date) else { return nil }
        let ts = dt.timeIntervalSince1970
        let computed = max(0, Int((ts - now) / 86400))
        return ChainExpiry(date: ts, dte: e.dte >= 0 ? e.dte : computed,
                           calls: e.calls.map(\.asYahoo), puts: e.puts.map(\.asYahoo))
    }
    guard !out.isEmpty else {
        throw APIError.server("No options data for \(sym)")
    }
    return (decoded.underlyingPrice, out.sorted { $0.dte < $1.dte })
}

// MARK: - Greeks (Black-Scholes, from contract IV)

struct ContractGreeks {
    let delta: Double
    let theta: Double   // $/day
    let gamma: Double
    let vega: Double    // $ per 1pt IV move
}

private let bsRate = 0.04

private func bsPhi(_ x: Double) -> Double {
    0.3989422804014327 * exp(-x * x / 2.0)
}

func greeksForContract(spot: Double, strike: Double, iv: Double, dte: Int, isPut: Bool) -> ContractGreeks {
    let t = max(Double(dte), 1) / 365.0
    let vol = max(iv, 0.01)
    let sqrtT = sqrt(t)
    let d1 = (log(spot / strike) + (bsRate + 0.5 * vol * vol) * t) / (vol * sqrtT)
    let d2 = d1 - vol * sqrtT
    let df = exp(-bsRate * t)
    let nd1 = bsNormCDF(d1)
    let delta = isPut ? nd1 - 1.0 : nd1
    let gamma = bsPhi(d1) / (spot * vol * sqrtT)
    let vega = spot * bsPhi(d1) * sqrtT / 100.0
    // Theta per year, then per day.
    let term1 = -(spot * bsPhi(d1) * vol) / (2 * sqrtT)
    let term2 = isPut ? bsRate * strike * df * bsNormCDF(-d2)
                      : -bsRate * strike * df * bsNormCDF(d2)
    let theta = (term1 + term2) / 365.0
    return ContractGreeks(delta: delta, theta: theta, gamma: gamma, vega: vega)
}
