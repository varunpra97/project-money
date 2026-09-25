import SwiftUI
import Charts

struct HomeView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var summary: PortfolioSummary?
    @State private var positions: [Position] = []
    @State private var quote: QuoteResponse?
    @State private var range: QuoteRange = .oneDay
    @State private var selectedDate: Date?
    @State private var expandedId: String?
    @State private var eventCache: [String: SymbolEvents] = [:]
    @State private var fomcDates: [String] = []
    @State private var eventsLoading = false
    @State private var positionMetric = "Total gain/loss"
    private let positionMetrics = ["Total gain/loss", "Today’s gain/loss", "Percent change", "Total equity"]

    private func positionValue(_ pos: Position) -> Double? {
        switch positionMetric {
        case "Today’s gain/loss": return pos.dayPnl
        case "Percent change": return pos.returnPct
        case "Total equity": return pos.equity
        default: return pos.unrealized
        }
    }

    private var metricNote: String {
        switch positionMetric {
        case "Today’s gain/loss": return "Unavailable: prior-day option marks have not been recorded."
        case "Percent change": return "Gain/loss as a percentage of opening premium, using saved marks."
        case "Total equity": return "Saved net option value; short positions are liabilities. Excludes collateral and underlying shares."
        default: return "Open-position gain/loss using saved marks, not live quotes."
        }
    }
    @State private var error: String?
    @State private var loading = true
    /// True when positions come from the synced Robinhood book.
    @State private var isLiveBook = false

    /// Headline chart tracks the largest position's underlying, else the S&P 500.
    private var chartSymbol: String { positions.first?.underlying ?? "SPY" }

    private var chartName: String {
        positions.isEmpty ? "S&P 500" : chartSymbol
    }

    private var points: [PricePoint] {
        pricePoints(from: quote?.bars ?? [])
    }

    private var scrubbed: PricePoint? {
        guard let d = selectedDate else { return nil }
        return nearestPoint(points, to: d)
    }

    private var chartPositive: Bool {
        (quote?.chgPct ?? summary?.dayPnlPct ?? 0) >= 0
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    headerSection
                    LiveStockPrice(symbol: chartSymbol)
                    chartSection
                    positionsSection
                    if let error {
                        ErrorCard(message: error) {
                            Task { await load() }
                        }
                    }
                }
                .padding()
            }
            .sensoryFeedback(.selection, trigger: range)
            .background(Color.pulseBg)
            .navigationTitle("Investing")
            .refreshable {
                APIClient.shared.invalidateCache()
                await load()
            }
            .task(id: scenePhase) {
                guard scenePhase == .active else { return }
                APIClient.shared.invalidateCache()
                await load()
            }
            .task(id: "refresh-\(scenePhase)") {
                guard scenePhase == .active else { return }
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .seconds(20)) } catch { return }
                    APIClient.shared.invalidateCache()
                    await load()
                }
            }
            .onChange(of: range) { _, _ in
                selectedDate = nil
                Task { await loadQuote() }
            }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            if loading && summary == nil {
                Text("$—.——")
                    .font(.system(size: 34, weight: .semibold))
                    .redacted(reason: .placeholder)
                    .shimmer()
            } else if let s = scrubbed {
                Text(money(s.close))
                    .font(.system(size: 34, weight: .semibold))
                    .heroNumber()
                Text(scrubDateLabel(s.date, range: range))
                    .font(.subheadline)
                    .foregroundStyle(Color.pulseSecondary)
            } else {
                Text(money(summary?.accountValue))
                    .font(.system(size: 34, weight: .semibold))
                    .heroNumber()
                if isLiveBook {
                    HStack(spacing: 6) {
                        Text("Live")
                            .foregroundStyle(Color.pulseGreen)
                        Text("· Buying power \(money(summary?.buyingPower))")
                            .foregroundStyle(Color.pulseSecondary)
                    }
                    .font(.subheadline.weight(.medium))
                } else {
                    HStack(spacing: 6) {
                        Text(signedMoney(summary?.dayPnl))
                        Text("(\(pct(summary?.dayPnlPct)))")
                        Text("Today")
                            .foregroundStyle(Color.pulseSecondary)
                    }
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(pnlColor(summary?.dayPnl))
                }
            }
        }
        .animation(.easeInOut(duration: 0.15), value: selectedDate)
    }

    // MARK: - Chart

    private var chartSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(chartName)
                    .font(.headline)
                Spacer()
                if let q = quote {
                    Text(pct(q.chgPct))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(pnlColor(q.chgPct))
                }
            }
            PriceChart(points: points, positive: chartPositive, selectedDate: $selectedDate)
                .redacted(reason: loading && quote == nil ? .placeholder : [])
            RangePicker(range: $range)
            if let quote { QuoteFreshness(quote: quote) }
        }
    }

    // MARK: - Positions

    private var positionsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Positions", subtitle: summary.map { "\($0.openPositions) open" + (isLiveBook ? " · live" : " · paper") })
            if !isLiveBook {
                Picker("Position value display", selection: $positionMetric) {
                    ForEach(positionMetrics, id: \.self) { Text($0).tag($0) }
                }
            }
            .pickerStyle(.menu)
            Text(metricNote).font(.caption).foregroundStyle(Color.pulseSecondary)
            NavigationLink {
                StressLabView()
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Stress Lab")
                            .font(.headline)
                        Text("Test a price shock, an IV jump and time decay on your book before you trade.")
                            .font(.caption)
                            .foregroundStyle(Color.pulseSecondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .foregroundStyle(Color.pulseTertiary)
                }
                .card()
            }
            .buttonStyle(.plain)
            if loading && positions.isEmpty {
                ForEach(0..<3, id: \.self) { _ in
                    RoundedRectangle(cornerRadius: 14)
                        .fill(Color.pulseCard)
                        .frame(height: 76)
                        .redacted(reason: .placeholder)
                        .shimmer()
                }
            } else if positions.isEmpty {
                Text(summary == nil ? "Positions have not loaded." : "No open positions recorded on this server.")
                    .font(.callout)
                    .foregroundStyle(Color.pulseSecondary)
                    .card()
            } else {
                ForEach(positions) { pos in
                    positionRow(pos)
                }
            }
        }
        .sensoryFeedback(.selection, trigger: expandedId)
    }

    @ViewBuilder
    private func positionRow(_ pos: Position) -> some View {
        if isLiveBook {
            livePositionRow(pos)
        } else {
            paperPositionRow(pos)
        }
    }

    /// Robinhood-style row: title, "expiry · size" subtitle, market-value pill.
    private func livePositionRow(_ pos: Position) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button {
                let willExpand = expandedId != pos.id
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedId = (expandedId == pos.id) ? nil : pos.id
                }
                if willExpand { loadEvents(for: pos.underlying) }
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(positionTitle(pos))
                            .font(.headline)
                        Text(positionSubtitle(pos))
                            .font(.caption)
                            .foregroundStyle(Color.pulseSecondary)
                            .lineLimit(1)
                    }
                    Spacer()
                    marketValuePill(pos)
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Color.pulseTertiary)
                        .rotationEffect(.degrees(expandedId == pos.id ? 180 : 0))
                }
            }
            .buttonStyle(.plain)

            if expandedId == pos.id {
                liveDetail(pos)
            }
        }
        .card()
    }

    private func paperPositionRow(_ pos: Position) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button {
                let willExpand = expandedId != pos.id
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedId = (expandedId == pos.id) ? nil : pos.id
                }
                if willExpand { loadEvents(for: pos.underlying) }
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(pos.underlying)
                            .font(.headline)
                        Text(pos.displayName)
                            .font(.caption)
                            .foregroundStyle(Color.pulseSecondary)
                            .lineLimit(1)
                        Text("Exp \(pos.expiry ?? "not recorded")")
                            .font(.caption2).foregroundStyle(Color.pulseSecondary)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(positionMetric == "Percent change" ? pct(positionValue(pos)) : positionMetric == "Total equity" ? money(positionValue(pos)) : signedMoney(positionValue(pos)))
                            .font(.headline)
                            .foregroundStyle(positionMetric == "Total equity" ? Color.primary : pnlColor(positionValue(pos)))
                        if let dte = pos.dte {
                            Text("\(dte) DTE")
                                .font(.caption)
                                .foregroundStyle(Color.pulseSecondary)
                        }
                    }
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Color.pulseTertiary)
                        .rotationEffect(.degrees(expandedId == pos.id ? 180 : 0))
                }
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                if let legs = pos.legs, !legs.isEmpty {
                    ForEach(Array(legs.enumerated()), id: \.offset) { _, leg in
                        Text("\(leg.side?.capitalized ?? "—") \(leg.quantity.map { String(format: "%g", $0) } ?? "—") · \(leg.optionType ?? "Option") · Strike \(money(leg.strike))")
                        if let expiry = leg.expiry {
                            Text("Exp \(expiry)")
                        }
                    }
                } else {
                    Text("Strike: Not recorded")
                }
            }
            .font(.caption)
            .foregroundStyle(Color.pulseSecondary)

            if expandedId == pos.id {
                creditRiskSection(pos)
                Divider().background(Color.primary.opacity(0.12))
                eventRiskSection(pos)
                Divider().background(Color.primary.opacity(0.12))
                LazyVGrid(
                    columns: [GridItem(.flexible(), alignment: .leading),
                              GridItem(.flexible(), alignment: .leading)],
                    spacing: 10
                ) {
                    stat("Strategy", pos.strategy)
                    stat("Quantity", pos.qty.map { String(format: "%.0f", $0) } ?? "—")
                    stat(pos.premiumDirection == "debit" ? "Opening debit (total)" : "Opening credit (total)", money(pos.openingValue ?? pos.credit.map { abs($0) }))
                    stat(pos.premiumDirection == "debit" ? "Close credit (total)" : "Close debit (total)", money(pos.closeValue))
                    stat("Net gain/loss", signedMoney(pos.unrealized))
                    stat("% of max profit", pct(pos.pctOfMaxProfit, signed: false))
                    stat("Days held", pos.daysHeld.map { String(format: "%.0f", $0) } ?? "—")
                    stat("Risk", pos.riskLabel ?? "—")
                    stat("Opened", relativeString(pos.openedAt))
                }
                Text("Close value uses the saved paper mark. \(pos.markAsOf.map { "Updated " + relativeString($0) } ?? "Mark time not recorded.")")
                    .font(.caption2).foregroundStyle(Color.pulseSecondary)
            }
        }
        .card()
    }

    // MARK: - Robinhood-style live rows

    private func positionTitle(_ pos: Position) -> String {
        if pos.strategy == "shares" { return pos.underlying }
        guard let legs = pos.legs, !legs.isEmpty else { return pos.displayName }
        let isPut = legs.first?.optionType == "put"
        let strikes = legs.compactMap(\.strike).sorted(by: >)
        let noun = legs.count > 1 ? (isPut ? "Puts" : "Calls") : (isPut ? "Put" : "Call")
        let s = strikes.map { "$" + String(format: "%g", $0) }.joined(separator: " / ")
        return "\(pos.underlying) \(s) \(noun)"
    }

    private func positionSubtitle(_ pos: Position) -> String {
        if pos.strategy == "shares" {
            return "\(pos.qty.map { String(format: "%g", $0) } ?? "—") Shares"
        }
        var parts: [String] = []
        if let e = shortExpiry(pos.expiry) { parts.append(e) }
        let q = pos.qty.map { String(format: "%.0f", $0) } ?? "—"
        parts.append("\(q) \(positionDescriptor(pos))")
        return parts.joined(separator: " · ")
    }

    private func positionDescriptor(_ pos: Position) -> String {
        let s = pos.strategy
        if s.contains("spread") { return pos.premiumDirection == "credit" ? "Credit Spreads" : "Debit Spreads" }
        if s.hasPrefix("long_") { return "Buys" }
        if s.hasPrefix("short_") { return "Sells" }
        return "Contracts"
    }

    private func shortExpiry(_ expiry: String?) -> String? {
        guard let expiry else { return nil }
        let parts = expiry.split(separator: "-")
        if parts.count >= 3, let m = Int(parts[1]), let d = Int(parts[2]) { return "\(m)/\(d)" }
        return nil
    }

    private func mediumExpiry(_ expiry: String?) -> String {
        guard let expiry else { return "—" }
        let parts = expiry.split(separator: "-")
        if parts.count >= 3, let m = Int(parts[1]), let d = Int(parts[2]) {
            return "\(m)/\(d)/\(parts[0].suffix(2))"
        }
        return expiry
    }

    private func signedQty(_ pos: Position) -> String {
        guard let q = pos.qty else { return "—" }
        if pos.strategy == "shares" { return String(format: "%g", q) }
        return String(format: "%g", pos.premiumDirection == "credit" ? -q : q)
    }

    private func marketValuePill(_ pos: Position) -> some View {
        Text(pos.equity.map { signedMoney($0) } ?? "—")
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(marketValuePillColor(pos.equity))
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func marketValuePillColor(_ v: Double?) -> Color {
        guard let v else { return Color.pulseTertiary }
        return v >= 0 ? Color.pulseGreen : Color.pulseRed
    }

    private func legTitle(_ underlying: String, _ leg: PositionLeg) -> String {
        let strike = leg.strike.map { "$" + String(format: "%g", $0) } ?? ""
        let kind = leg.optionType == "put" ? "Put" : "Call"
        return "\(underlying) \(strike) \(kind)".trimmingCharacters(in: .whitespaces)
    }

    private func legSubtitle(_ leg: PositionLeg) -> String {
        var parts: [String] = []
        if let e = shortExpiry(leg.expiry) { parts.append(e) }
        let q = leg.quantity.map { String(format: "%g", $0) } ?? "—"
        parts.append("\(q) \((leg.side == "sell") ? "Sells" : "Buys")")
        return parts.joined(separator: " · ")
    }

    /// Per-contract price, like Robinhood's leg rows.
    private func legPrice(_ leg: PositionLeg) -> String {
        guard let v = leg.value, let q = leg.quantity, q > 0 else { return "—" }
        return money(abs(v) / (q * 100))
    }

    /// Expanded "Your position" detail for the real book.
    private func liveDetail(_ pos: Position) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your position")
                .font(.headline)
            LazyVGrid(
                columns: [GridItem(.flexible(), alignment: .leading),
                          GridItem(.flexible(), alignment: .leading)],
                spacing: 10
            ) {
                stat("Quantity", signedQty(pos))
                stat("Market value", signedMoney(pos.equity))
                if pos.strategy != "shares" {
                    stat("Expiration date", mediumExpiry(pos.expiry))
                }
                stat("Tracked since", relativeString(pos.openedAt))
            }
            if let legs = pos.legs, !legs.isEmpty {
                Text("Options")
                    .font(.headline)
                    .padding(.top, 4)
                ForEach(Array(legs.enumerated()), id: \.offset) { idx, leg in
                    VStack(alignment: .leading, spacing: 0) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(legTitle(pos.underlying, leg))
                                    .font(.subheadline)
                                Text(legSubtitle(leg))
                                    .font(.caption)
                                    .foregroundStyle(Color.pulseSecondary)
                            }
                            Spacer()
                            Text(legPrice(leg))
                                .font(.subheadline)
                        }
                        .padding(.vertical, 6)
                        if idx < legs.count - 1 {
                            Divider().background(Color.primary.opacity(0.08))
                        }
                    }
                }
            }
            if let risk = pos.maxLoss, risk > 0 {
                HStack {
                    Text("Max risk")
                        .font(.caption)
                        .foregroundStyle(Color.pulseSecondary)
                    Spacer()
                    Text(money(risk))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Color.pulseRed)
                }
            }
            Divider().background(Color.primary.opacity(0.12))
            eventRiskSection(pos)
        }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(Color.pulseSecondary)
            Text(value)
                .font(.subheadline.weight(.medium))
        }
    }

    /// Credit collected vs max risk for an expanded position.
    private func creditRiskSection(_ pos: Position) -> some View {
        let isDebit = pos.premiumDirection == "debit"
        let creditLabel = isDebit ? "Debit paid" : "Credit collected"
        let creditAmt = abs(pos.credit ?? 0)
        let risk = pos.riskAmount
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(creditLabel)
                        .font(.caption)
                        .foregroundStyle(Color.pulseSecondary)
                    Text(money(creditAmt))
                        .font(.headline)
                        .foregroundStyle(isDebit ? Color.primary : Color.pulseGreen)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("Max risk")
                        .font(.caption)
                        .foregroundStyle(Color.pulseSecondary)
                    Text(risk.map { money($0) } ?? "—")
                        .font(.headline)
                        .foregroundStyle(risk == nil ? Color.pulseSecondary : Color.pulseRed)
                }
            }
            if let risk, risk > 0 {
                let total = creditAmt + risk
                GeometryReader { geo in
                    HStack(spacing: 0) {
                        Rectangle()
                            .fill(isDebit ? Color.orange : Color.pulseGreen)
                            .frame(width: geo.size.width * CGFloat(creditAmt / total))
                        Rectangle()
                            .fill(Color.pulseRed.opacity(0.75))
                            .frame(width: geo.size.width * CGFloat(risk / total))
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                }
                .frame(height: 8)
                if !isDebit, creditAmt > 0 {
                    Text("Risk/reward 1 : \(String(format: "%.1f", risk / creditAmt))")
                        .font(.caption2)
                        .foregroundStyle(Color.pulseSecondary)
                }
            } else {
                Text("Max risk is not defined for this position (unlimited or not recorded).")
                    .font(.caption2)
                    .foregroundStyle(Color.pulseSecondary)
            }
        }
        .padding(12)
        .background(Color.primary.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Loading

    private func load() async {
        loading = true
        error = nil
        do {
            do {
                // Real Robinhood book first; paper book when no snapshot
                // has synced yet (404).
                async let s = APIClient.shared.brokerageSummary()
                async let p = APIClient.shared.brokeragePositions()
                let (ss, pp) = try await (s, p)
                guard !Task.isCancelled else { return }
                summary = ss
                positions = pp
                isLiveBook = true
            } catch APIError.http(let code) where code == 404 {
                async let s = APIClient.shared.summary()
                async let p = APIClient.shared.positions()
                let (ss, pp) = try await (s, p)
                guard !Task.isCancelled else { return }
                summary = ss
                positions = pp
                isLiveBook = false
            }
            await loadQuote()
        } catch {
            if !Task.isCancelled { self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription }
        }
        loading = false
    }

    private func loadQuote() async {
        let requestedSymbol=chartSymbol
        let requestedRange=range
        do {
            let result=try await APIClient.shared.quote(requestedSymbol, range: requestedRange)
            guard requestedSymbol == chartSymbol && requestedRange == range && !Task.isCancelled else {return}
            quote=result
        } catch {
            if !Task.isCancelled { self.error="Chart refresh failed. Showing the last dated chart. " + error.localizedDescription }
        }
    }

    // MARK: - Event risk

    private func loadEvents(for symbol: String) {
        let sym = symbol.uppercased()
        guard eventCache[sym] == nil, !eventsLoading else { return }
        eventsLoading = true
        Task {
            do {
                let resp = try await APIClient.shared.events(symbols: [sym])
                await MainActor.run {
                    if let ev = resp.events[sym] { eventCache[sym] = ev }
                    fomcDates = resp.fomcDates
                    eventsLoading = false
                }
            } catch {
                await MainActor.run { eventsLoading = false }
            }
        }
    }

    private func eventRiskSection(_ pos: Position) -> some View {
        let items = riskItems(for: pos.underlying.uppercased())
        return VStack(alignment: .leading, spacing: 8) {
            Text("Event risk")
                .font(.caption)
                .foregroundStyle(Color.pulseSecondary)
            if eventsLoading && eventCache[pos.underlying.uppercased()] == nil {
                ProgressView().scaleEffect(0.8)
            } else if items.isEmpty {
                Text("No earnings, dividend, or Fed dates in the next 45 days.")
                    .font(.caption)
                    .foregroundStyle(Color.pulseSecondary)
            } else {
                ForEach(items) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Text(item.icon)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title)
                                .font(.caption.weight(.semibold))
                            Text(item.note)
                                .font(.caption)
                                .foregroundStyle(Color.pulseSecondary)
                        }
                    }
                }
            }
        }
    }

    private func riskItems(for symbol: String) -> [EventRiskItem] {
        var items: [EventRiskItem] = []
        let ev = eventCache[symbol]
        if let d = ev?.earningsDate, let days = daysUntil(d), days >= 0, days <= 45 {
            items.append(EventRiskItem(
                icon: "\u{1F4CA}",
                title: "Earnings \(prettyDate(d)) \u{00B7} \(days)d out",
                note: "The stock can gap overnight on the print. Option spreads often widen into the event, so exits get pricier.",
                daysOut: days))
        }
        if let d = ev?.exDividendDate, let days = daysUntil(d), days >= 0, days <= 45 {
            items.append(EventRiskItem(
                icon: "\u{1F4B5}",
                title: "Ex-dividend \(prettyDate(d)) \u{00B7} \(days)d out",
                note: "The stock usually drops by the dividend amount at the open. Short calls can be assigned early when the dividend beats the remaining time value.",
                daysOut: days))
        }
        for d in fomcDates {
            if let days = daysUntil(d), days >= 0, days <= 45 {
                items.append(EventRiskItem(
                    icon: "\u{1F3E6}",
                    title: "Fed decision \(prettyDate(d)) \u{00B7} \(days)d out",
                    note: "Rate decisions can swing the whole market. Index-correlated positions feel it most \u{2014} volatility usually jumps into the announcement.",
                    daysOut: days))
                break
            }
        }
        return items.sorted { $0.daysOut < $1.daysOut }
    }

    private func daysUntil(_ isoDate: String) -> Int? {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(secondsFromGMT: 0)
        guard let d = fmt.date(from: isoDate) else { return nil }
        let cal = Calendar.current
        return cal.dateComponents([.day], from: cal.startOfDay(for: Date()), to: cal.startOfDay(for: d)).day
    }

    private func prettyDate(_ isoDate: String) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(secondsFromGMT: 0)
        guard let d = fmt.date(from: isoDate) else { return isoDate }
        let out = DateFormatter()
        out.dateFormat = "MMM d"
        return out.string(from: d)
    }
}

struct SymbolEvents: Decodable {
    let earningsDate: String?
    let exDividendDate: String?
    enum CodingKeys: String, CodingKey {
        case earningsDate = "earnings_date"
        case exDividendDate = "ex_dividend_date"
    }
}

struct EventsResponse: Decodable {
    let events: [String: SymbolEvents]
    let fomcDates: [String]
    enum CodingKeys: String, CodingKey {
        case events
        case fomcDates = "fomc_dates"
    }
}

struct EventRiskItem: Identifiable {
    let id = UUID()
    let icon: String
    let title: String
    let note: String
    let daysOut: Int
}
