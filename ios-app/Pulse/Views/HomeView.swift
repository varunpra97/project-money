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
            SectionHeader("Positions", subtitle: summary.map { "\($0.openPositions) open" })
            Picker("Position value display", selection: $positionMetric) {
                ForEach(positionMetrics, id: \.self) { Text($0).tag($0) }
            }
            .pickerStyle(.menu)
            Text(metricNote).font(.caption).foregroundStyle(Color.pulseSecondary)
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

    private func positionRow(_ pos: Position) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedId = (expandedId == pos.id) ? nil : pos.id
                }
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
                Divider().background(Color.black.opacity(0.08))
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
        .background(Color.black.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Loading

    private func load() async {
        loading = true
        error = nil
        do {
            async let s = APIClient.shared.summary()
            async let p = APIClient.shared.positions()
            let (ss, pp) = try await (s, p)
            guard !Task.isCancelled else { return }
            summary = ss
            positions = pp
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
}
