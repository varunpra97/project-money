import SwiftUI

struct DiscoverView: View {
    @State private var celebrity: CelebrityResponse?
    @State private var earnings: EarningsResponse?
    @State private var volatility: VolatilityResponse?
    @State private var candidates: [Candidate] = []
    @State private var error: String?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let error, !loading {
                        ErrorCard(message: error) {
                            Task { await load() }
                        }
                    }
                    celebritySection
                    earningsSection
                    volatilitySection
                    candidatesSection
                    Text("Insights are context only — not trade signals.")
                        .font(.footnote)
                        .foregroundStyle(Color.pulseTertiary)
                        .padding(.top, 4)
                }
                .padding()
            }
            .background(Color.pulseBg)
            .navigationTitle("Discover")
            .refreshable { await load() }
            .task { await load() }
        }
    }

    // MARK: - Celebrity moves

    private var celebritySection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("⭐ Celebrity moves",
                          subtitle: celebrity.map { "Scan \($0.scanDate)" } ?? "Ranked fund & disclosure moves")
            if loading && celebrity == nil {
                placeholderCards(2)
            } else {
                ForEach((celebrity?.moves ?? []).prefix(8)) { m in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(m.symbol)
                                .font(.headline)
                            if let heat = m.heat {
                                Pill(text: "🔥 \(heat)", color: .orange)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(money(m.livePrice, digits: 2))
                                    .font(.subheadline.weight(.semibold))
                                Text(pct(m.liveChgPct))
                                    .font(.caption)
                                    .foregroundStyle(pnlColor(m.liveChgPct))
                            }
                        }
                        Text(m.company)
                            .font(.caption)
                            .foregroundStyle(Color.pulseSecondary)
                        Text(m.investor)
                            .font(.subheadline.weight(.medium))
                        Text(m.whatChanged)
                            .font(.callout)
                            .foregroundStyle(Color.pulseSecondary)
                    }
                    .card()
                }
            }
        }
    }

    // MARK: - Earnings radar

    private var earningsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("📅 Earnings radar", subtitle: "Upcoming reports in the tracker universe")
            if loading && earnings == nil {
                placeholderCards(3, height: 64)
            } else {
                ForEach(earnings?.rows ?? [EarningsRow]()) { row in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.symbol)
                                .font(.headline)
                            Text(row.company)
                                .font(.caption)
                                .foregroundStyle(Color.pulseSecondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            Text(row.earningsDate)
                                .font(.subheadline.weight(.medium))
                            earningsPill(row)
                        }
                    }
                    .card()
                }
            }
        }
    }

    private func earningsPill(_ row: EarningsRow) -> some View {
        Group {
            switch row.status {
            case "Upcoming":
                Pill(text: "📅 \(row.when)", color: .pulseGreen)
            case "Just reported":
                Pill(text: "🆕 \(row.when)", color: .blue)
            default:
                Pill(text: row.when, color: .pulseTertiary)
            }
        }
    }

    // MARK: - Volatility watch

    private var volatilitySection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("🌊 Volatility watch", subtitle: "Recent movers in the tracker universe")
            if loading && volatility == nil {
                placeholderCards(3, height: 84)
            } else {
                ForEach(volatility?.rows ?? [VolatilityRow]()) { row in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.symbol)
                                    .font(.headline)
                                Text(row.company)
                                    .font(.caption)
                                    .foregroundStyle(Color.pulseSecondary)
                                    .lineLimit(1)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(money(row.last))
                                    .font(.subheadline.weight(.semibold))
                                Text(pct(row.chg1dPct))
                                    .font(.caption)
                                    .foregroundStyle(pnlColor(row.chg1dPct))
                            }
                        }
                        HStack(spacing: 12) {
                            miniStat("20d vol", pct(row.vol20dAnnPct, digits: 1, signed: false))
                            miniStat("Max 1d", pct(row.max1dMove10dPct, digits: 1, signed: false))
                            miniStat("ATR14", pct(row.atr14Pct, digits: 1, signed: false))
                            Spacer()
                            if row.volatile == true {
                                Pill(text: "⚡ Volatile", color: .orange)
                            }
                        }
                        if let reasons = row.reasons, !reasons.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 6) {
                                    ForEach(reasons, id: \.self) { r in
                                        Pill(text: r, color: .pulseSecondary)
                                    }
                                }
                            }
                        }
                    }
                    .card()
                }
            }
        }
    }

    private func miniStat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(Color.pulseTertiary)
            Text(value)
                .font(.caption.weight(.semibold))
        }
    }

    // MARK: - Candidates rail

    private var candidatesSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Top candidates", subtitle: "Paper-trading ideas from the latest scan")
            if loading && candidates.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(0..<3, id: \.self) { _ in
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.pulseCard)
                                .frame(width: 220, height: 120)
                                .redacted(reason: .placeholder)
                        }
                    }
                }
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(candidates.prefix(10)) { c in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(c.symbol)
                                    .font(.headline)
                                Text(c.displayName)
                                    .font(.caption)
                                    .foregroundStyle(Color.pulseSecondary)
                                    .lineLimit(2)
                                Spacer()
                                HStack {
                                    if let dte = c.dte {
                                        Text("\(dte) DTE")
                                            .font(.caption2)
                                            .foregroundStyle(Color.pulseTertiary)
                                    }
                                    Spacer()
                                    if let bias = c.bias {
                                        Pill(text: bias, color: biasColor(bias))
                                    }
                                }
                            }
                            .frame(width: 200, height: 120, alignment: .topLeading)
                            .card()
                        }
                    }
                }
            }
        }
    }

    private func biasColor(_ bias: String) -> Color {
        let b = bias.lowercased()
        if b.contains("bull") { return .pulseGreen }
        if b.contains("bear") { return .pulseRed }
        return .pulseSecondary
    }

    // MARK: - Helpers

    private func placeholderCards(_ n: Int, height: CGFloat = 110) -> some View {
        VStack(spacing: 10) {
            ForEach(0..<n, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.pulseCard)
                    .frame(height: height)
                    .redacted(reason: .placeholder)
            }
        }
    }

    private func load() async {
        loading = true
        error = nil
        do {
            async let c = APIClient.shared.celebrity()
            async let e = APIClient.shared.earnings()
            async let v = APIClient.shared.volatility()
            async let k = APIClient.shared.candidates()
            let (cc, ee, vv, kk) = try await (c, e, v, k)
            celebrity = cc
            earnings = ee
            volatility = vv
            candidates = kk
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        loading = false
    }
}
