import Foundation

// MARK: - Health

struct HealthResponse: Decodable {
    let ok: Bool
}

// MARK: - Portfolio

struct Greeks: Decodable {
    let delta: Double?
    let theta: Double?
    let gamma: Double?
    let vega: Double?
    // The API also sends non-numeric flags (e.g. "estimated"); those are ignored.
}

struct PortfolioSummary: Decodable {
    let accountValue: Double
    let buyingPower: Double
    let dayPnl: Double
    let dayPnlPct: Double
    let totalPnl: Double
    let openPositions: Int
    let greeks: Greeks?
    let asOf: String

    enum CodingKeys: String, CodingKey {
        case accountValue = "account_value"
        case buyingPower = "buying_power"
        case dayPnl = "day_pnl"
        case dayPnlPct = "day_pnl_pct"
        case totalPnl = "total_pnl"
        case openPositions = "open_positions"
        case greeks
        case asOf = "as_of"
    }
}

struct PositionLeg: Decodable {
    let side: String?
    let optionType: String?
    let strike: Double?
    let quantity: Double?
    let expiry: String?

    enum CodingKeys: String, CodingKey {
        case side, strike, quantity, expiry
        case optionType = "option_type"
    }
}

struct Position: Decodable, Identifiable {    let id: String
    let underlying: String
    let strategy: String
    let displayName: String
    let openedAt: String
    let dte: Int?
    let qty: Double?
    let credit: Double?
    let unrealized: Double?
    let pctOfMaxProfit: Double?
    let daysHeld: Double?
    let riskLabel: String?
    let expiry: String?
    let legs: [PositionLeg]?
    let dayPnl: Double?
    let returnPct: Double?
    let equity: Double?
    let openingValue: Double?
    let closeValue: Double?
    let premiumDirection: String?
    let markAsOf: String?

    enum CodingKeys: String, CodingKey {
        case id
        case underlying
        case strategy
        case displayName = "display_name"
        case openedAt = "opened_at"
        case dte
        case qty
        case credit
        case unrealized
        case pctOfMaxProfit = "pct_of_max_profit"
        case daysHeld = "days_held"
        case riskLabel = "risk_label"
        case expiry, legs, equity
        case dayPnl = "day_pnl"
        case returnPct = "return_pct"
        case openingValue = "opening_value"
        case closeValue = "close_value"
        case premiumDirection = "premium_direction"
        case markAsOf = "mark_as_of"
    }
}

struct ActivityItem: Decodable, Identifiable {    let id = UUID()
    let ts: String
    let kind: String
    let text: String
    let amount: Double?

    enum CodingKeys: String, CodingKey {
        case ts
        case kind
        case text
        case amount
    }
}

struct PositionsResponse: Decodable {
    let positions: [Position]
}

struct ActivityResponse: Decodable {
    let activity: [ActivityItem]
}

struct CandidatesResponse: Decodable {
    let candidates: [Candidate]
}

// MARK: - Insights

struct CelebrityMove: Decodable, Identifiable {
    var id: String { symbol }
    let rank: Int?
    let symbol: String
    let company: String
    let investor: String
    let whatChanged: String
    let period: String
    let why: String
    let heat: Int?
    let livePrice: Double?
    let liveChgPct: Double?

    enum CodingKeys: String, CodingKey {
        case rank
        case symbol
        case company
        case investor
        case whatChanged = "what_changed"
        case period
        case why
        case heat
        case livePrice = "live_price"
        case liveChgPct = "live_chg_pct"
    }
}

struct CelebrityResponse: Decodable {
    let scanDate: String
    let moves: [CelebrityMove]

    enum CodingKeys: String, CodingKey {
        case scanDate = "scan_date"
        case moves
    }
}

struct EarningsRow: Decodable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let company: String
    let earningsDate: String
    let when: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case symbol
        case company
        case earningsDate = "earnings_date"
        case when
        case status
    }
}

struct EarningsResponse: Decodable {
    let asOf: String
    let fresh: Bool
    let rows: [EarningsRow]

    enum CodingKeys: String, CodingKey {
        case asOf = "as_of"
        case fresh
        case rows
    }
}

struct VolatilityRow: Decodable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let company: String
    let last: Double?
    let chg1dPct: Double?
    let chg5dPct: Double?
    let vol20dAnnPct: Double?
    let max1dMove10dPct: Double?
    let atr14Pct: Double?
    let volatile: Bool?
    let reasons: [String]?

    enum CodingKeys: String, CodingKey {
        case symbol
        case company
        case last
        case chg1dPct = "chg_1d_pct"
        case chg5dPct = "chg_5d_pct"
        case vol20dAnnPct = "vol_20d_ann_pct"
        case max1dMove10dPct = "max_1d_move_10d_pct"
        case atr14Pct = "atr14_pct"
        case volatile
        case reasons
    }
}

struct VolatilityResponse: Decodable {
    let asOf: String
    let fresh: Bool
    let rows: [VolatilityRow]

    enum CodingKeys: String, CodingKey {
        case asOf = "as_of"
        case fresh
        case rows
    }
}

struct Candidate: Decodable, Identifiable {
    var id: String { symbol + strategy }
    let symbol: String
    let company: String?
    let strategy: String
    let displayName: String
    let dte: Int?
    let bias: String?
    let creditStatus: String?
    let rationale: String?

    enum CodingKeys: String, CodingKey {
        case symbol
        case company
        case strategy
        case displayName = "display_name"
        case dte
        case bias
        case creditStatus = "credit_status"
        case rationale
    }
}

// MARK: - Quote

struct Bar: Decodable {
    let t: TimeInterval
    let c: Double
    let o: Double?
    let h: Double?
    let l: Double?
    let v: Double?

    enum CodingKeys: String, CodingKey {
        case t
        case c, o, h, l, v
    }
}

struct QuoteResponse: Decodable {
    let symbol: String
    let price: Double?
    let chgPct: Double?
    let bars: [Bar]
    let asOf: String?
    let source: String?
    let cacheStale: Bool?
    let cacheAgeSeconds: Double?
    let cacheWarning: String?
    let fresh: Bool?

    enum CodingKeys: String, CodingKey {
        case symbol
        case price
        case chgPct = "chg_pct"
        case bars
        case asOf = "as_of"
        case source, fresh
        case cacheStale = "cache_stale"
        case cacheAgeSeconds = "cache_age_seconds"
        case cacheWarning = "cache_warning"
    }
}

struct SymbolDetails: Decodable {
    let symbol: String
    let as_of: String
    let source: String
    let volatility: VolatilityRow?
    let earnings: EarningsRow?
    let warnings: [String]
}
