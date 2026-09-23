import Foundation

// MARK: - ThetaHedge direct fetch (app.thetahedge.io, no login required)
//
// The ticker-list API is open: POST /api/stock-table with the JSON body the
// site's own client sends. We query per symbol and exact-match client-side.

private let thetaHedgeURL = URL(string: "https://app.thetahedge.io/api/stock-table")!

func fetchThetaHedgeRow(symbol: String) async throws -> ThetaHedgeRow? {
    let sym = symbol.uppercased()
    let body: [String: Any] = [
        "limit_val": 20,
        "offset_val": 0,
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
    // search_symbol is a substring match; keep only the exact symbol.
    return rows.first
}

// MARK: - Yahoo Finance options chain (free, no key)
//
// GET https://query1.finance.yahoo.com/v7/finance/options/{SYMBOL}
// ?date={expiration unix} — omit for the front expiration; expirationDates
// lists all available expiries.

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

struct YahooExpirationSet: Decodable {
    let expirationDate: Int
    let calls: [YahooOptionContract]
    let puts: [YahooOptionContract]
}

struct YahooChainQuote: Decodable {
    let regularMarketPrice: Double?
}

struct YahooChainResult: Decodable {
    let underlyingSymbol: String?
    let expirationDates: [Int]?
    let quote: YahooChainQuote?
    let options: [YahooExpirationSet]
}

struct YahooChainResponse: Decodable {
    struct Chain: Decodable {
        struct ChainError: Decodable {
            let code: String?
            let description: String?
        }
        let result: [YahooChainResult]?
        let error: ChainError?
    }
    let optionChain: Chain
}

struct ChainExpiry {
    let date: TimeInterval   // unix seconds
    let dte: Int
    let calls: [YahooOptionContract]
    let puts: [YahooOptionContract]
}

func fetchOptionsChain(symbol: String) async throws -> (spot: Double?, expiries: [ChainExpiry]) {
    let sym = symbol.uppercased().addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? symbol.uppercased()
    guard let url = URL(string: "https://query1.finance.yahoo.com/v7/finance/options/\(sym)") else {
        throw APIError.badURL("options/\(sym)")
    }
    var req = URLRequest(url: url)
    // Yahoo blocks default URLSession user agents; a browser UA works without a crumb.
    req.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", forHTTPHeaderField: "User-Agent")
    req.setValue("application/json", forHTTPHeaderField: "Accept")
    req.timeoutInterval = 25
    let (data, resp) = try await URLSession.shared.data(for: req)
    guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
        throw APIError.http((resp as? HTTPURLResponse)?.statusCode ?? -1)
    }
    let decoded = try JSONDecoder().decode(YahooChainResponse.self, from: data)
    if let err = decoded.optionChain.error, err.code != nil {
        throw APIError.server(err.description ?? "Yahoo options unavailable")
    }
    guard let result = decoded.optionChain.result?.first else {
        throw APIError.server("No options data for \(sym)")
    }
    let now = Date().timeIntervalSince1970
    var out: [ChainExpiry] = []
    var seenDates = Set<Int>()
    // The front page returns only the nearest expiry; pull the rest we need.
    let wantedDates = (result.expirationDates ?? []).filter { Double($0) > now + 5 * 86400 }
    for set in result.options where !seenDates.contains(set.expirationDate) {
        seenDates.insert(set.expirationDate)
        out.append(ChainExpiry(date: TimeInterval(set.expirationDate),
                              dte: max(0, Int((Double(set.expirationDate) - now) / 86400)),
                              calls: set.calls, puts: set.puts))
    }
    for ts in wantedDates where !seenDates.contains(ts) {
        seenDates.insert(ts)
        if let extra = try? await fetchExpiry(symbol: sym, date: ts) {
            out.append(extra)
        }
        if out.count >= 6 { break } // enough to find the ~14 DTE one
    }
    out.sort { $0.dte < $1.dte }
    return (result.quote?.regularMarketPrice, out)
}

private func fetchExpiry(symbol: String, date: Int) async throws -> ChainExpiry {
    guard let url = URL(string: "https://query1.finance.yahoo.com/v7/finance/options/\(symbol)?date=\(date)") else {
        throw APIError.badURL("options/\(symbol)")
    }
    var req = URLRequest(url: url)
    req.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", forHTTPHeaderField: "User-Agent")
    req.setValue("application/json", forHTTPHeaderField: "Accept")
    req.timeoutInterval = 20
    let (data, resp) = try await URLSession.shared.data(for: req)
    guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
        throw APIError.http((resp as? HTTPURLResponse)?.statusCode ?? -1)
    }
    let decoded = try JSONDecoder().decode(YahooChainResponse.self, from: data)
    guard let set = decoded.optionChain.result?.first?.options.first else {
        throw APIError.server("No contracts for expiry")
    }
    let now = Date().timeIntervalSince1970
    return ChainExpiry(date: TimeInterval(set.expirationDate),
                       dte: max(0, Int((Double(set.expirationDate) - now) / 86400)),
                       calls: set.calls, puts: set.puts)
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
