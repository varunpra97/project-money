import SwiftUI

// MARK: - Scan models (/api/scan envelope, stock-data-scanner.scan/v0.1)

struct ScanSuggestedLeg: Decodable, Identifiable {
    var id: String { "\(right ?? "?")-\(strike)-\(expiration ?? "dte\(dte ?? 0)")" }
    let strike: Double
    let dte: Int?
    let delta: Double?
    let premium: Double?
    let bid: Double?
    let ask: Double?
    let mid: Double?
    let openInterest: Int?
    let right: String?
    let expiration: String?
    let side: String?
    let strategyHint: String?

    var midPrice: Double? {
        if let mid { return mid }
        if let bid, let ask { return (bid + ask) / 2 }
        if let premium { return abs(premium) }
        return nil
    }

    enum CodingKeys: String, CodingKey {
        case strike, dte, delta, premium, bid, ask, mid, openInterest, right, expiration, side, strategyHint
    }
}

struct ScanTrend: Decodable {
    let bias: String?
    let sma20: Double?
    let sma50: Double?
    let sma200: Double?
    let priceVsSma50Pct: Double?
}

struct ScanLiquidity: Decodable {
    let volume: Double?
    let avgVolume: Double?
    let volumeRatio: Double?
}

struct ScanEarnings: Decodable {
    let nextDate: String?
    let daysToEarnings: Int?
}

struct ScanOptionsBlock: Decodable {
    let iv: Double?
    let ivRank: Double?
    let ivPercentile: Double?
    let impliedMovePct: Double?
    let strategyName: String?
    let legs: [ScanSuggestedLeg]

    private enum Keys: String, CodingKey {
        case iv, ivRank, ivPercentile, impliedMovePct, suggested
    }
    private struct LegsObject: Decodable {
        let legs: [ScanSuggestedLeg]?
        let strategy: String?
        let name: String?
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        iv = try c.decodeIfPresent(Double.self, forKey: .iv)
        ivRank = try c.decodeIfPresent(Double.self, forKey: .ivRank)
        ivPercentile = try c.decodeIfPresent(Double.self, forKey: .ivPercentile)
        impliedMovePct = try c.decodeIfPresent(Double.self, forKey: .impliedMovePct)
        var legs: [ScanSuggestedLeg] = []
        var strategyName: String? = nil
        if let arr = try? c.decodeIfPresent([ScanSuggestedLeg].self, forKey: .suggested) {
            legs = arr
        } else if let obj = try? c.decodeIfPresent(LegsObject.self, forKey: .suggested) {
            legs = obj.legs ?? []
            strategyName = obj.strategy ?? obj.name
        }
        self.legs = legs
        self.strategyName = strategyName
    }
}

struct ScanResult: Decodable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let name: String?
    let price: Double?
    let changePct: Double?
    let marketCap: Double?
    let fiftyTwoWeekHigh: Double?
    let fiftyTwoWeekLow: Double?
    let trend: ScanTrend?
    let liquidity: ScanLiquidity?
    let earnings: ScanEarnings?
    let options: ScanOptionsBlock?
    /// Volatility rankings merged by the backend (ThetaHedge), when available.
    let theta: ThetaHedgeRow?

    enum CodingKeys: String, CodingKey {
        case symbol, name, price, changePct, marketCap, fiftyTwoWeekHigh, fiftyTwoWeekLow
        case trend, liquidity, earnings, options, theta
    }
}

struct ScanEnvelope: Decodable {
    let asOf: String?
    let source: String?
    let universe: [String]?
    let results: [ScanResult]
}

// MARK: - ThetaHedge volatility rankings (/api/thetahedge)

struct ThetaHedgeRow: Decodable {
    let symbol: String?
    let name: String?
    let price: Double?
    let iv30: Double?
    let ivRank: Double?
    let hv30: Double?
    let avgPutYield30d: Double?
    let avgCallYield30d: Double?
    let wheelRank: Int?
    let wheelScore: Double?
    let wheelAvgPutYield3m: Double?
    let wheelAvgCallYield3m: Double?
    let daysToEarnings: Int?
    let finalRating: String?
    let sector: String?
    let putIv30d: Double?
    let callIv30d: Double?

    enum CodingKeys: String, CodingKey {
        case symbol, name, price, iv30, hv30, sector
        case ivRank = "iv_rank"
        case avgPutYield30d = "avg_30d_put_yield"
        case avgCallYield30d = "avg_30d_call_yield"
        case wheelRank = "wheel_rank"
        case wheelScore = "wheel_score"
        case wheelAvgPutYield3m = "wheel_avg_put_yield_3m"
        case wheelAvgCallYield3m = "wheel_avg_call_yield_3m"
        case daysToEarnings = "days_to_earnings"
        case finalRating = "final_rating"
        case putIv30d = "put_30d_iv"
        case callIv30d = "call_30d_iv"
    }
}

struct ThetaHedgeResponse: Decodable {
    let asOf: String?
    let total: Int?
    let rows: [ThetaHedgeRow]?
}

// MARK: - Scanner output list

enum ScanSort: String, CaseIterable, Identifiable {
    case wheelRank = "Wheel rank"
    case ivRank = "IV rank"
    case movers = "Movers"

    var id: String { rawValue }
}

struct ScannerView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var envelope: ScanEnvelope?
    @State private var directTheta: [String: ThetaHedgeRow] = [:]
    @State private var strategies: [String: String] = [:]
    @State private var sort = ScanSort.wheelRank
    @State private var error: String?
    @State private var loading = true

    /// Backend-merged ThetaHedge row first, direct fetch fallback second.
    private func thetaFor(_ r: ScanResult) -> ThetaHedgeRow? {
        r.theta ?? directTheta[r.symbol]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let error, !loading {
                    ErrorCard(message: error) {
                        Task { await load() }
                    }
                }
                headerSection
                if loading && envelope == nil {
                    placeholderRows
                } else {
                    sortPicker
                    ForEach(sortedResults()) { r in
                        NavigationLink(destination: ScannerDetailView(
                            result: r,
                            theta: thetaFor(r),
                            strategy: strategies[r.symbol]
                        )) {
                            scanRow(r)
                        }
                        .buttonStyle(.plain)
                    }
                }
                Text("Scanner output is context for paper trading — not trade signals.")
                    .font(.footnote)
                    .foregroundStyle(Color.pulseTertiary)
                    .padding(.top, 4)
            }
            .padding()
        }
        .background(Color.pulseBg)
        .navigationTitle("Scanner output")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable {
            APIClient.shared.invalidateCache()
            await load()
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            APIClient.shared.invalidateCache()
            await load()
        }
    }

    private var headerSection: some View {
        SectionHeader("Latest scan", subtitle: scanSubtitle)
    }

    private var scanSubtitle: String? {
        var bits: [String] = []
        if let asOf = envelope?.asOf { bits.append("as of \(asOf)") }
        let ranked = (envelope?.results ?? []).filter { thetaFor($0)?.wheelRank != nil }.count
        bits.append(ranked > 0 ? "volatility ranked \(ranked)" : "volatility pending")
        if let n = envelope?.results.count { bits.append("\(n) tickers") }
        return bits.isEmpty ? nil : bits.joined(separator: " · ")
    }

    private var sortPicker: some View {
        Picker("Sort", selection: $sort) {
            ForEach(ScanSort.allCases) { s in Text(s.rawValue).tag(s) }
        }
        .pickerStyle(.segmented)
    }

    private func sortedResults() -> [ScanResult] {
        let rows = envelope?.results ?? []
        switch sort {
        case .wheelRank:
            return rows.sorted {
                let a = thetaFor($0)?.wheelRank ?? Int.max
                let b = thetaFor($1)?.wheelRank ?? Int.max
                return a == b ? $0.symbol < $1.symbol : a < b
            }
        case .ivRank:
            return rows.sorted {
                let a = $0.options?.ivRank ?? thetaFor($0)?.ivRank ?? -1
                let b = $1.options?.ivRank ?? thetaFor($1)?.ivRank ?? -1
                return a == b ? $0.symbol < $1.symbol : a > b
            }
        case .movers:
            return rows.sorted {
                abs($0.changePct ?? 0) > abs($1.changePct ?? 0)
            }
        }
    }

    private func scanRow(_ r: ScanResult) -> some View {
        let theta = thetaFor(r)
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(r.symbol)
                        .font(.headline)
                    if let name = r.name ?? theta?.name {
                        Text(name)
                            .font(.caption)
                            .foregroundStyle(Color.pulseSecondary)
                            .lineLimit(1)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(money(r.price ?? theta?.price))
                        .font(.subheadline.weight(.semibold))
                        .heroNumber()
                    Text(pct(r.changePct))
                        .font(.caption)
                        .foregroundStyle(pnlColor(r.changePct))
                }
            }
            HStack(spacing: 6) {
                if let bias = r.trend?.bias, !bias.isEmpty {
                    Pill(text: bias.capitalized, color: biasColor(bias))
                }
                if let strategy = strategies[r.symbol] {
                    Pill(text: strategyName(strategy), color: .blue)
                } else if let sn = r.options?.strategyName {
                    Pill(text: sn, color: .blue)
                }
                if let wr = theta?.wheelRank {
                    Pill(text: "🎡 #\(wr)", color: .orange)
                }
                if let ivr = r.options?.ivRank ?? theta?.ivRank {
                    Pill(text: "IV \(String(format: "%.0f", ivr))", color: .pulseSecondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(Color.pulseTertiary)
            }
        }
        .card()
    }

    private func biasColor(_ bias: String) -> Color {
        let b = bias.lowercased()
        if b.contains("bull") { return .pulseGreen }
        if b.contains("bear") { return .pulseRed }
        return .pulseSecondary
    }

    private func strategyName(_ s: String) -> String {
        s.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private var placeholderRows: some View {
        VStack(spacing: 10) {
            ForEach(0..<5, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.pulseCard)
                    .frame(height: 92)
                    .redacted(reason: .placeholder)
                    .shimmer()
            }
        }
    }

    private func load() async {
        loading = true
        error = nil
        do {
            let env: ScanEnvelope = try await APIClient.shared.scan()
            envelope = env
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        do {
            let cands: [Candidate] = try await APIClient.shared.candidates()
            var map: [String: String] = [:]
            for c in cands { map[c.symbol] = c.strategy }
            strategies = map
        } catch {
            strategies = [:]
        }
        await backfillTheta()
        loading = false
    }

    /// Fetch ThetaHedge rows directly for symbols the backend hasn't merged yet.
    private func backfillTheta() async {
        guard let results = envelope?.results else { return }
        let missing = results.filter { $0.theta?.wheelRank == nil }.map(\.symbol)
        guard !missing.isEmpty else { return }
        await withTaskGroup(of: (String, ThetaHedgeRow?).self) { group in
            for sym in missing {
                group.addTask {
                    let row = try? await fetchThetaHedgeRow(symbol: sym)
                    return (sym, row)
                }
            }
            for await (sym, row) in group {
                if let row { directTheta[sym] = row }
            }
        }
    }
}

// MARK: - Black-Scholes helpers (strike estimation when scanner legs are blank)

/// Shared with OptionsData.swift for chain-based Greeks.
func bsNormCDF(_ x: Double) -> Double {
    // Abramowitz–Stegun approximation; no platform math beyond exp/log.
    let t = 1.0 / (1.0 + 0.2316419 * abs(x))
    let d = 0.3989422804014327 * exp(-x * x / 2.0)
    let p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    return x > 0 ? 1.0 - p : p
}

private func bsD1(price: Double, strike: Double, iv: Double, dte: Int) -> Double {
    let t = max(Double(dte), 1) / 365.0
    let vol = max(iv, 0.01)
    return (log(price / strike) + (0.04 + 0.5 * vol * vol) * t) / (vol * sqrt(t))
}

private func bsPutDelta(price: Double, strike: Double, iv: Double, dte: Int) -> Double {
    bsNormCDF(bsD1(price: price, strike: strike, iv: iv, dte: dte)) - 1.0
}

private func bsCallDelta(price: Double, strike: Double, iv: Double, dte: Int) -> Double {
    bsNormCDF(bsD1(price: price, strike: strike, iv: iv, dte: dte))
}

private func bsPutPrice(price: Double, strike: Double, iv: Double, dte: Int) -> Double {
    let t = max(Double(dte), 1) / 365.0
    let d1 = bsD1(price: price, strike: strike, iv: iv, dte: dte)
    let d2 = d1 - max(iv, 0.01) * sqrt(t)
    let df = exp(-0.04 * t)
    return strike * df * bsNormCDF(-d2) - price * bsNormCDF(-d1)
}

private func bsCallPrice(price: Double, strike: Double, iv: Double, dte: Int) -> Double {
    let t = max(Double(dte), 1) / 365.0
    let d1 = bsD1(price: price, strike: strike, iv: iv, dte: dte)
    let d2 = d1 - max(iv, 0.01) * sqrt(t)
    let df = exp(-0.04 * t)
    return price * bsNormCDF(d1) - strike * df * bsNormCDF(d2)
}

// MARK: - Spread recommendation

struct SpreadPick {
    let kind: String          // "Put credit spread" / "Call credit spread"
    let shortStrike: Double
    let longStrike: Double
    let dte: Int
    let expirationLabel: String?
    let shortDelta: Double
    let credit: Double
    let maxProfit: Double
    let maxLoss: Double
    let breakeven: Double
    let estimated: Bool       // true = modeled from IV, false = real quotes or scanner legs
    let sourceLabel: String   // "Live chain" / "Scanner" / "IV estimate"

    var width: Double { abs(shortStrike - longStrike) }
    var pop: Double { max(0, min(1, 1 - abs(shortDelta))) }
}

/// Picks the ~14-DTE credit-spread recommendation for a scan result.
/// Prefers the scanner's own suggested legs; falls back to a delta-targeted
/// estimate from IV (clearly labeled as estimated).
private func recommendSpread(result: ScanResult, theta: ThetaHedgeRow?, strategy: String?) -> SpreadPick? {
    guard let price = result.price, price > 0 else { return nil }
    let s = (strategy ?? result.options?.strategyName ?? "").lowercased()
    let bias = (result.trend?.bias ?? "").lowercased()
    let isPut: Bool
    if s.contains("put") && s.contains("spread") { isPut = true }
    else if s.contains("call") && s.contains("spread") { isPut = false }
    else { isPut = bias != "bearish" }

    let right = isPut ? "put" : "call"
    let legs = (result.options?.legs ?? []).filter { ($0.right ?? "").lowercased() == right }

    // 1) Scanner legs, when the collector has populated them.
    if let sell = legs.first(where: { ($0.side ?? "").lowercased() == "sell" }),
       let buy = legs.first(where: { ($0.side ?? "").lowercased() == "buy" }),
       let sellMid = sell.midPrice, let buyMid = buy.midPrice {
        let credit = max(sellMid - buyMid, 0)
        let width = abs(sell.strike - buy.strike)
        let dte = sell.dte ?? buy.dte ?? 14
        let breakeven = isPut ? sell.strike - credit : sell.strike + credit
        return SpreadPick(
            kind: isPut ? "Put credit spread" : "Call credit spread",
            shortStrike: sell.strike, longStrike: buy.strike, dte: dte,
            expirationLabel: sell.expiration ?? buy.expiration,
            shortDelta: sell.delta ?? 0, credit: credit,
            maxProfit: credit, maxLoss: max(width - credit, 0), breakeven: breakeven,
            estimated: false, sourceLabel: "Scanner"
        )
    }

    // 2) Estimate: short ~30Δ leg on the standard strike ladder, 14 DTE.
    let ivRaw = theta?.iv30 ?? result.options?.iv
    guard let ivRaw, ivRaw > 0 else { return nil }
    let iv = ivRaw > 1.5 ? ivRaw / 100.0 : ivRaw   // ThetaHedge quotes IV30 as percent
    let dte = 14
    let step: Double = price >= 200 ? 5 : price >= 50 ? 1 : 0.5
    var bestStrike: Double? = nil
    var bestDelta = 0.0
    var bestScore = Double.infinity
    for i in 1...40 {
        let k = isPut ? price - Double(i) * step : price + Double(i) * step
        guard k > 0 else { continue }
        let d = isPut ? bsPutDelta(price: price, strike: k, iv: iv, dte: dte)
                      : bsCallDelta(price: price, strike: k, iv: iv, dte: dte)
        let score = abs(abs(d) - 0.30)
        if score < bestScore { bestScore = score; bestStrike = k; bestDelta = d }
    }
    guard let shortK = bestStrike else { return nil }
    let longK = isPut ? shortK - 2 * step : shortK + 2 * step
    let shortPx = isPut ? bsPutPrice(price: price, strike: shortK, iv: iv, dte: dte)
                        : bsCallPrice(price: price, strike: shortK, iv: iv, dte: dte)
    let longPx = isPut ? bsPutPrice(price: price, strike: longK, iv: iv, dte: dte)
                       : bsCallPrice(price: price, strike: longK, iv: iv, dte: dte)
    let credit = max(shortPx - longPx, 0.01)
    let width = abs(shortK - longK)
    let breakeven = isPut ? shortK - credit : shortK + credit
    return SpreadPick(
        kind: isPut ? "Put credit spread" : "Call credit spread",
        shortStrike: shortK, longStrike: longK, dte: dte,
        expirationLabel: nil,
        shortDelta: bestDelta, credit: credit,
        maxProfit: credit, maxLoss: max(width - credit, 0), breakeven: breakeven,
        estimated: true, sourceLabel: "IV estimate"
    )
}

// MARK: - Scanner detail

struct ScannerDetailView: View {
    let result: ScanResult
    let theta: ThetaHedgeRow?
    let strategy: String?

    @State private var chainSpot: Double?
    @State private var chainExpiries: [ChainExpiry] = []
    @State private var chainLoading = true

    /// Put credit spread for bullish/neutral bias, call credit spread for bearish.
    private var spreadIsPut: Bool {
        let s = (strategy ?? result.options?.strategyName ?? "").lowercased()
        let bias = (result.trend?.bias ?? "").lowercased()
        if s.contains("put") && s.contains("spread") { return true }
        if s.contains("call") && s.contains("spread") { return false }
        return bias != "bearish"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header
                scanSection
                if let theta {
                    volatilitySection(theta)
                }
                optionsSection
                greeksSection
                spreadSection
                Text("Paper-trading context only — not trade signals.")
                    .font(.footnote)
                    .foregroundStyle(Color.pulseTertiary)
            }
            .padding()
        }
        .background(Color.pulseBg)
        .navigationTitle(result.symbol)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadChain()
        }
    }

    private func loadChain() async {
        do {
            let (spot, expiries) = try await fetchOptionsChain(symbol: result.symbol)
            chainSpot = spot
            chainExpiries = expiries
        } catch {
            chainExpiries = []
        }
        chainLoading = false
    }

    private func expiryDateLabel(_ ts: TimeInterval) -> String {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .none
        return f.string(from: Date(timeIntervalSince1970: ts))
    }

    // MARK: Live chain spread (~14 DTE, ~30Δ short leg)

    private struct ChainLeg {
        let contract: YahooOptionContract
        let greeks: ContractGreeks
        let side: String
    }

    private func chainSpread() -> (pick: SpreadPick, short: ChainLeg, long: ChainLeg)? {
        guard !chainLoading,
              let expiry = chainExpiries.min(by: { abs($0.dte - 14) < abs($1.dte - 14) }),
              expiry.dte >= 5,
              let spot = chainSpot ?? result.price, spot > 0
        else { return nil }
        let isPut = spreadIsPut
        let contracts = (isPut ? expiry.puts : expiry.calls)
            .filter { $0.mid != nil && ($0.impliedVolatility ?? 0) > 0 }
            .sorted { $0.strike < $1.strike }
        guard !contracts.isEmpty else { return nil }
        var bestIdx: Int? = nil
        var bestScore = Double.infinity
        for (i, c) in contracts.enumerated() {
            let g = greeksForContract(spot: spot, strike: c.strike, iv: c.impliedVolatility ?? 0.3,
                                      dte: expiry.dte, isPut: isPut)
            let score = abs(abs(g.delta) - 0.30)
            if score < bestScore { bestScore = score; bestIdx = i }
        }
        guard let si = bestIdx else { return nil }
        let li = isPut ? si - 2 : si + 2
        guard contracts.indices.contains(li) else { return nil }
        let shortC = contracts[si]
        let longC = contracts[li]
        guard let shortMid = shortC.mid, let longMid = longC.mid else { return nil }
        let longG = greeksForContract(spot: spot, strike: longC.strike, iv: longC.impliedVolatility ?? 0.3,
                                      dte: expiry.dte, isPut: isPut)
        let credit = max(shortMid - longMid, 0.01)
        let width = abs(shortC.strike - longC.strike)
        let breakeven = isPut ? shortC.strike - credit : shortC.strike + credit
        let shortG = greeksForContract(spot: spot, strike: shortC.strike, iv: shortC.impliedVolatility ?? 0.3,
                                       dte: expiry.dte, isPut: isPut)
        let pick = SpreadPick(
            kind: isPut ? "Put credit spread" : "Call credit spread",
            shortStrike: shortC.strike, longStrike: longC.strike, dte: expiry.dte,
            expirationLabel: expiryDateLabel(expiry.date),
            shortDelta: shortG.delta, credit: credit,
            maxProfit: credit, maxLoss: max(width - credit, 0), breakeven: breakeven,
            estimated: false, sourceLabel: "Live chain"
        )
        return (pick,
                ChainLeg(contract: shortC, greeks: shortG, side: "Sell"),
                ChainLeg(contract: longC, greeks: longG, side: "Buy"))
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(result.symbol)
                .font(.title.weight(.bold))
            if let name = result.name ?? theta?.name {
                Text(name)
                    .font(.subheadline)
                    .foregroundStyle(Color.pulseSecondary)
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(money(result.price ?? theta?.price))
                    .font(.title2.weight(.semibold))
                    .heroNumber()
                Text(pct(result.changePct))
                    .font(.subheadline)
                    .foregroundStyle(pnlColor(result.changePct))
            }
        }
    }

    // MARK: Scan data

    private var scanSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Scan", subtitle: strategy.map { "Strategy: \($0.replacingOccurrences(of: "_", with: " ").capitalized)" })
            VStack(spacing: 8) {
                if let bias = result.trend?.bias {
                    kvRow("Trend bias", bias.capitalized)
                }
                kvRow("52-week range", "\(money(result.fiftyTwoWeekLow, digits: 0)) – \(money(result.fiftyTwoWeekHigh, digits: 0))")
                kvRow("Price vs SMA50", pct(result.trend?.priceVsSma50Pct, digits: 1))
                if let vr = result.liquidity?.volumeRatio {
                    kvRow("Volume ratio", String(format: "%.2f×", vr))
                }
                if let dte = result.earnings?.daysToEarnings {
                    kvRow("Days to earnings", "\(dte)")
                }
                if let mc = result.marketCap {
                    kvRow("Market cap", compactMoney(mc))
                }
            }
            .card()
        }
    }

    private func kvRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .font(.callout)
                .foregroundStyle(Color.pulseSecondary)
            Spacer()
            Text(value)
                .font(.callout.weight(.medium))
        }
    }

    private func compactMoney(_ v: Double) -> String {
        if v >= 1e12 { return String(format: "$%.2fT", v / 1e12) }
        if v >= 1e9 { return String(format: "$%.1fB", v / 1e9) }
        if v >= 1e6 { return String(format: "$%.0fM", v / 1e6) }
        return money(v, digits: 0)
    }

    // MARK: Volatility

    private func volatilitySection(_ t: ThetaHedgeRow) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Volatility · ThetaHedge", subtitle: "Option-selling attractiveness")
            VStack(spacing: 8) {
                if let wr = t.wheelRank {
                    HStack {
                        Text("Wheel rank")
                            .font(.callout)
                            .foregroundStyle(Color.pulseSecondary)
                        Spacer()
                        Text("#\(wr)")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(.orange)
                    }
                }
                kvRow("30Δ put yield", pct(t.avgPutYield30d, digits: 2, signed: false))
                kvRow("30Δ call yield", pct(t.avgCallYield30d, digits: 2, signed: false))
                kvRow("IV30", pct(t.iv30, digits: 1, signed: false))
                if let ivr = t.ivRank {
                    kvRow("IV rank", String(format: "%.0f", ivr))
                }
                if let fr = t.finalRating {
                    kvRow("Rating", fr)
                }
            }
            .card()
        }
    }

    // MARK: Options pricing

    private var optionsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Options pricing", subtitle: legsSubtitle)
            if let cs = chainSpread() {
                chainLegCard(cs.short, right: spreadIsPut ? "Put" : "Call")
                chainLegCard(cs.long, right: spreadIsPut ? "Put" : "Call")
                if chainLoading {
                    Text("Refreshing live chain…")
                        .font(.caption)
                        .foregroundStyle(Color.pulseTertiary)
                }
            } else if !legs.isEmpty {
                ForEach(legs) { leg in
                    legCard(leg)
                }
            } else if chainLoading {
                VStack(spacing: 10) {
                    ForEach(0..<2, id: \.self) { _ in
                        RoundedRectangle(cornerRadius: 14)
                            .fill(Color.pulseCard)
                            .frame(height: 76)
                            .redacted(reason: .placeholder)
                            .shimmer()
                    }
                }
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    Text("No option quotes available for \(result.symbol).")
                        .font(.callout)
                        .foregroundStyle(Color.pulseSecondary)
                    Text("The scanner's options collector hasn't populated legs yet, and the live chain lookup failed.")
                        .font(.caption)
                        .foregroundStyle(Color.pulseTertiary)
                }
                .card()
            }
        }
    }

    private var legs: [ScanSuggestedLeg] {
        result.options?.legs ?? []
    }

    private var legsSubtitle: String? {
        if let sn = result.options?.strategyName ?? strategy {
            return "Suggested: \(sn.replacingOccurrences(of: "_", with: " ").capitalized)"
        }
        return legs.isEmpty ? nil : "Suggested legs"
    }

    private func chainLegCard(_ leg: ChainLeg, right: String) -> some View {
        let c = leg.contract
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(leg.side) \(right) \(money(c.strike, digits: 0))")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Pill(text: "Live", color: .pulseGreen)
            }
            HStack(spacing: 14) {
                legStat("Mid", c.mid.map { money($0) } ?? "—")
                if let bid = c.bid, let ask = c.ask {
                    legStat("Bid/Ask", "\(money(bid))/\(money(ask))")
                }
                if let iv = c.impliedVolatility {
                    legStat("IV", pct(iv * 100, digits: 1, signed: false))
                }
                if let oi = c.openInterest {
                    legStat("OI", "\(oi)")
                }
                Spacer()
            }
        }
        .card()
    }

    private func legCard(_ leg: ScanSuggestedLeg) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(leg.side?.capitalized ?? "") \(leg.right?.capitalized ?? "") \(money(leg.strike, digits: 0))")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                if let dte = leg.dte {
                    Pill(text: "\(dte) DTE", color: .pulseSecondary)
                }
            }
            HStack(spacing: 14) {
                legStat("Mid", leg.midPrice.map { money($0) } ?? "—")
                if let bid = leg.bid, let ask = leg.ask {
                    legStat("Bid/Ask", "\(money(bid))/\(money(ask))")
                }
                if let d = leg.delta {
                    legStat("Δ", String(format: "%.2f", d))
                }
                if let oi = leg.openInterest {
                    legStat("OI", "\(oi)")
                }
                Spacer()
                if let exp = leg.expiration {
                    Text(exp)
                        .font(.caption2)
                        .foregroundStyle(Color.pulseTertiary)
                }
            }
        }
        .card()
    }

    private func legStat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(Color.pulseTertiary)
            Text(value)
                .font(.caption.weight(.semibold))
        }
    }

    // MARK: Greeks

    private var greeksSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Greeks", subtitle: greeksSubtitle)
            if let cs = chainSpread() {
                VStack(spacing: 8) {
                    chainGreeksRow(cs.short, right: spreadIsPut ? "Put" : "Call")
                    chainGreeksRow(cs.long, right: spreadIsPut ? "Put" : "Call")
                    Text("Modeled from each contract's implied volatility (Black-Scholes).")
                        .font(.caption)
                        .foregroundStyle(Color.pulseTertiary)
                }
                .card()
            } else if !legs.isEmpty {
                VStack(spacing: 8) {
                    ForEach(legs) { leg in
                        HStack {
                            Text("\(leg.right?.capitalized ?? "?") \(money(leg.strike, digits: 0))")
                                .font(.callout)
                                .foregroundStyle(Color.pulseSecondary)
                            Spacer()
                            HStack(spacing: 12) {
                                greekChip("Δ", leg.delta)
                            }
                        }
                    }
                    Text("The scan reports delta per leg; theta, gamma, and vega are not in the scan output yet.")
                        .font(.caption)
                        .foregroundStyle(Color.pulseTertiary)
                }
                .card()
            } else {
                Text("No Greeks to show — option quotes haven't loaded for this ticker yet.")
                    .font(.callout)
                    .foregroundStyle(Color.pulseSecondary)
                    .card()
            }
        }
    }

    private var greeksSubtitle: String? {
        chainSpread() != nil ? "Live chain legs" : "Per suggested leg"
    }

    private func chainGreeksRow(_ leg: ChainLeg, right: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("\(leg.side) \(right) \(money(leg.contract.strike, digits: 0))")
                .font(.callout)
                .foregroundStyle(Color.pulseSecondary)
            HStack(spacing: 16) {
                greekChip("Δ", leg.greeks.delta, digits: 3)
                greekChip("Θ/day", leg.greeks.theta, digits: 2)
                greekChip("Γ", leg.greeks.gamma, digits: 4)
                greekChip("Vega", leg.greeks.vega, digits: 2)
                Spacer()
            }
        }
    }

    private func greekChip(_ label: String, _ value: Double?, digits: Int = 3) -> some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(Color.pulseTertiary)
            Text(value.map { String(format: "%.\(digits)f", $0) } ?? "—")
                .font(.caption.weight(.semibold))
        }
    }

    // MARK: Credit spread recommendation (~14 DTE)

    private var spreadSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("🎯 Credit spread · ~14 DTE", subtitle: spreadSubtitle)
            if let cs = chainSpread() {
                spreadCard(pick: cs.pick)
                Text("Short leg targets ~30Δ on the live chain; long leg sits 2 strikes further out. Premiums are live mid quotes.")
                    .font(.caption)
                    .foregroundStyle(Color.pulseTertiary)
            } else if let pick = recommendSpread(result: result, theta: theta, strategy: strategy) {
                spreadCard(pick: pick)
                if pick.estimated {
                    Text("Strikes are modeled from IV at ~30Δ on the standard strike ladder, and premiums are Black-Scholes estimates — real bid/ask will differ. Paper-trading context only.")
                        .font(.caption)
                        .foregroundStyle(Color.pulseTertiary)
                }
            } else if chainLoading {
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.pulseCard)
                    .frame(height: 220)
                    .redacted(reason: .placeholder)
                    .shimmer()
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Can't recommend strikes yet.")
                        .font(.callout)
                        .foregroundStyle(Color.pulseSecondary)
                    Text("A price and an IV reading (scan options or ThetaHedge) are needed to target the ~30Δ short leg for a 2-week spread.")
                        .font(.caption)
                        .foregroundStyle(Color.pulseTertiary)
                }
                .card()
            }
        }
    }

    private func spreadCard(pick: SpreadPick) -> some View {
        VStack(spacing: 8) {
            HStack {
                Text(pick.kind)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Pill(text: pick.sourceLabel,
                     color: pick.sourceLabel == "Live chain" ? .pulseGreen
                        : pick.estimated ? .orange : .blue)
            }
            Divider().background(Color.pulseTertiary.opacity(0.4))
            kvRow("Sell", money(pick.shortStrike, digits: 0))
            kvRow("Buy", money(pick.longStrike, digits: 0))
            kvRow("Width", money(pick.width, digits: 0))
            if let exp = pick.expirationLabel {
                kvRow("Expiration", exp)
            } else {
                kvRow("Target DTE", "\(pick.dte)")
            }
            kvRow("Short Δ", String(format: "%.2f", pick.shortDelta))
            Divider().background(Color.pulseTertiary.opacity(0.4))
            kvRow("Est. credit", money(pick.credit))
            kvRow("Max profit", money(pick.maxProfit))
            kvRow("Max loss", money(pick.maxLoss))
            kvRow("Breakeven", money(pick.breakeven, digits: 2))
            kvRow("Est. win prob", pct(pick.pop * 100, digits: 0, signed: false))
        }
        .card()
    }

    private var spreadSubtitle: String? {
        if chainSpread() != nil { return nil }
        if legs.isEmpty {
            return "Put credit spread or call credit spread, by trend bias"
        }
        return nil
    }
}
