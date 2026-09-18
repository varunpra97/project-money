import SwiftUI
import Charts

struct SearchView: View {
    @State private var symbol = ""
    @State private var quote: QuoteResponse?
    @State private var range: QuoteRange = .oneDay
    @State private var selectedDate: Date?
    @State private var earningsRow: EarningsRow?
    @State private var volatilityRow: VolatilityRow?
    @State private var error: String?
    @State private var loading = false
    @State private var searched = false

    private var points: [PricePoint] {
        pricePoints(from: quote?.bars ?? [])
    }

    private var scrubbed: PricePoint? {
        guard let d = selectedDate else { return nil }
        return nearestPoint(points, to: d)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    searchField
                    if loading {
                        loadingState
                    } else if let q = quote {
                        quoteHeader(q)
                        chartSection(q)
                        statsGrid
                        flagsSection
                    } else if let error {
                        ErrorCard(message: error) {
                            Task { await search() }
                        }
                    } else if !searched {
                        emptyState
                    }
                }
                .padding()
            }
            .background(Color.pulseBg)
            .navigationTitle("Search")
            .onChange(of: range) { _, _ in
                selectedDate = nil
                Task { await reloadQuote() }
            }
        }
    }

    // MARK: - Search field

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.pulseSecondary)
            TextField("Symbol, e.g. AAPL", text: $symbol)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .submitLabel(.search)
                .onSubmit { Task { await search() } }
            if !symbol.isEmpty {
                Button {
                    symbol = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.pulseSecondary)
                }
            }
        }
        .padding(12)
        .background(Color.pulseCard)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    // MARK: - Quote

    private func quoteHeader(_ q: QuoteResponse) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(q.symbol)
                .font(.title.weight(.bold))
            if let s = scrubbed {
                Text(money(s.close))
                    .font(.system(size: 32, weight: .semibold))
                Text(scrubDateLabel(s.date, range: range))
                    .font(.subheadline)
                    .foregroundStyle(.pulseSecondary)
            } else {
                Text(money(q.price))
                    .font(.system(size: 32, weight: .semibold))
                Text(pct(q.chgPct))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(pnlColor(q.chgPct))
            }
        }
        .animation(.easeInOut(duration: 0.15), value: selectedDate)
    }

    private func chartSection(_ q: QuoteResponse) -> some View {
        VStack(spacing: 8) {
            PriceChart(
                points: points,
                positive: (q.chgPct ?? 0) >= 0,
                selectedDate: $selectedDate
            )
            RangePicker(range: $range)
        }
    }

    // MARK: - Stats & flags

    private var statsGrid: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Key stats")
            LazyVGrid(
                columns: [GridItem(.flexible(), alignment: .leading),
                          GridItem(.flexible(), alignment: .leading)],
                spacing: 10
            ) {
                statCell("20d volatility", pct(volatilityRow?.vol20dAnnPct, digits: 1, signed: false))
                statCell("Biggest 1d move (10d)", pct(volatilityRow?.max1dMove10dPct, signed: false))
                statCell("ATR(14)", pct(volatilityRow?.atr14Pct, signed: false))
                statCell("5d change", pct(volatilityRow?.chg5dPct))
                statCell("Earnings", earningsRow?.earningsDate ?? "—")
                statCell("Earnings timing", earningsRow?.when ?? "—")
            }
        }
    }

    private func statCell(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.pulseSecondary)
            Text(value)
                .font(.headline)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
    }

    @ViewBuilder
    private var flagsSection: some View {
        if let row = volatilityRow, row.volatile == true {
            VStack(alignment: .leading, spacing: 8) {
                SectionHeader("⚡ Volatility flags")
                ForEach(row.reasons ?? [], id: \.self) { r in
                    HStack(spacing: 8) {
                        Image(systemName: "bolt.fill")
                            .foregroundStyle(.orange)
                            .font(.caption)
                        Text(r)
                            .font(.callout)
                    }
                    .card()
                }
            }
        }
        if let e = earningsRow, e.status != "—" {
            VStack(alignment: .leading, spacing: 8) {
                SectionHeader("📅 Earnings")
                HStack {
                    Text("Earnings \(e.earningsDate)")
                    Spacer()
                    Pill(text: e.status == "Upcoming" ? "📅 \(e.when)" : "🆕 \(e.when)",
                         color: e.status == "Upcoming" ? .pulseGreen : .blue)
                }
                .card()
            }
        }
    }

    // MARK: - States

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.largeTitle)
                .foregroundStyle(.pulseTertiary)
            Text("Look up any symbol for a live quote, chart, and volatility check.")
                .font(.callout)
                .foregroundStyle(.pulseSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 60)
    }

    private var loadingState: some View {
        VStack(alignment: .leading, spacing: 12) {
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.pulseCard)
                .frame(width: 140, height: 36)
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.pulseCard)
                .frame(height: 220)
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.pulseCard)
                .frame(height: 120)
        }
        .redacted(reason: .placeholder)
    }

    // MARK: - Loading

    private func search() async {
        let sym = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !sym.isEmpty else { return }
        symbol = sym
        searched = true
        loading = true
        error = nil
        quote = nil
        earningsRow = nil
        volatilityRow = nil
        selectedDate = nil
        do {
            async let q = APIClient.shared.quote(sym, range: range)
            async let e = APIClient.shared.earnings()
            async let v = APIClient.shared.volatility()
            let (qq, ee, vv) = try await (q, e, v)
            quote = qq
            earningsRow = ee.rows.first { $0.symbol.uppercased() == sym }
            volatilityRow = vv.rows.first { $0.symbol.uppercased() == sym }
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        loading = false
    }

    private func reloadQuote() async {
        let sym = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !sym.isEmpty, quote != nil else { return }
        do {
            quote = try await APIClient.shared.quote(sym, range: range)
        } catch {
            // Keep the existing chart on refresh failure.
        }
    }
}
