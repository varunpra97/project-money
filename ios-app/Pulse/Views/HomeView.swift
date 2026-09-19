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
                    await loadQuote()
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
            } else if let s = scrubbed {
                Text(money(s.close))
                    .font(.system(size: 34, weight: .semibold))
                Text(scrubDateLabel(s.date, range: range))
                    .font(.subheadline)
                    .foregroundStyle(Color.pulseSecondary)
            } else {
                Text(money(summary?.accountValue))
                    .font(.system(size: 34, weight: .semibold))
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
                }
            } else if positions.isEmpty {
                Text("No open positions.")
                    .font(.callout)
                    .foregroundStyle(Color.pulseSecondary)
                    .card()
            } else {
                ForEach(positions) { pos in
                    positionRow(pos)
                }
            }
        }
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
                Text("Expiration: \(pos.expiry ?? "Not recorded")")
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
                Divider().background(Color.white.opacity(0.08))
                LazyVGrid(
                    columns: [GridItem(.flexible(), alignment: .leading),
                              GridItem(.flexible(), alignment: .leading)],
                    spacing: 10
                ) {
                    stat("Strategy", pos.strategy)
                    stat("Quantity", pos.qty.map { String(format: "%.0f", $0) } ?? "—")
                    stat("Credit", money(pos.credit))
                    stat("% of max profit", pct(pos.pctOfMaxProfit, signed: false))
                    stat("Days held", pos.daysHeld.map { String(format: "%.0f", $0) } ?? "—")
                    stat("Risk", pos.riskLabel ?? "—")
                    stat("Opened", relativeString(pos.openedAt))
                }
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

    // MARK: - Loading

    private func load() async {
        loading = true
        error = nil
        do {
            async let s = APIClient.shared.summary()
            async let p = APIClient.shared.positions()
            let (ss, pp) = try await (s, p)
            summary = ss
            positions = pp
            await loadQuote()
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        loading = false
    }

    private func loadQuote() async {
        do {
            quote = try await APIClient.shared.quote(chartSymbol, range: range)
        } catch {
            // Keep the previous chart; the header still shows account value.
        }
    }
}
