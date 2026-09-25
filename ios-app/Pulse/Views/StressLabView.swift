import SwiftUI

// MARK: - Stress lab models

struct StressScenario: Decodable {
    let priceMovePct: Double
    let volJumpPct: Double
    let daysForward: Double

    enum CodingKeys: String, CodingKey {
        case priceMovePct = "price_move_pct"
        case volJumpPct = "vol_jump_pct"
        case daysForward = "days_forward"
    }

    var summary: String {
        let move = String(format: "%+.0f%%", priceMovePct)
        let vol = String(format: "+%.0f%%", volJumpPct)
        let days = String(format: "%.0f", daysForward)
        return "\(move) move · \(vol) IV · \(days)d decay"
    }
}

struct StressTotals: Decodable {
    let baseValue: Double
    let stressedValue: Double
    let pnl: Double

    enum CodingKeys: String, CodingKey {
        case baseValue = "base_value"
        case stressedValue = "stressed_value"
        case pnl
    }
}

struct StressPositionResult: Decodable, Identifiable {
    let id: String
    let underlying: String
    let strategy: String
    let displayName: String
    let baseValue: Double?
    let stressedValue: Double?
    let pnl: Double?
    let pnlPct: Double?
    let note: String?

    enum CodingKeys: String, CodingKey {
        case id, underlying, strategy, note
        case displayName = "display_name"
        case baseValue = "base_value"
        case stressedValue = "stressed_value"
        case pnl, pnlPct = "pnl_pct"
    }
}

struct StressTestResponse: Decodable {
    let scenario: StressScenario
    let asOf: String
    let totals: StressTotals
    let positions: [StressPositionResult]

    enum CodingKeys: String, CodingKey {
        case scenario, totals, positions
        case asOf = "as_of"
    }
}

// MARK: - Stress lab view

/// Volatility stress lab: test a price move, an IV jump, and time decay
/// against the paper book before opening a trade.
struct StressLabView: View {
    @State private var priceMove: Double = -10
    @State private var volJump: Double = 50
    @State private var daysForward: Double = 1
    @State private var result: StressTestResponse?
    @State private var running = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                introCard
                controlsCard
                runButton
                if running { ProgressView("Stressing the book…").tint(.pulseGreen) }
                if let error { ErrorCard(message: error) { Task { await run() } } }
                if let result { resultsSection(result) }
            }
            .padding()
        }
        .background(Color.pulseBg)
        .navigationTitle("Stress Lab")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var introCard: some View {
        Text("See what a price shock, a volatility jump, and time decay would do to your paper book before you open a trade.")
            .font(.subheadline)
            .foregroundStyle(Color.pulseSecondary)
            .card()
    }

    private var controlsCard: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Price move")
                    Spacer()
                    Text(String(format: "%+.0f%%", priceMove))
                        .fontWeight(.semibold)
                        .foregroundStyle(pnlColor(priceMove))
                }
                .font(.subheadline)
                Slider(value: $priceMove, in: -25...25, step: 1)
                    .tint(priceMove >= 0 ? .pulseGreen : .pulseRed)
            }
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Volatility jump")
                    Spacer()
                    Text(String(format: "+%.0f%%", volJump)).fontWeight(.semibold)
                }
                .font(.subheadline)
                Slider(value: $volJump, in: 0...100, step: 5)
                    .tint(.pulseGreen)
            }
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Days of decay")
                    Spacer()
                    Text(String(format: "%.0f day%@", daysForward, daysForward == 1 ? "" : "s"))
                        .fontWeight(.semibold)
                }
                .font(.subheadline)
                Slider(value: $daysForward, in: 0...7, step: 1)
                    .tint(.pulseGreen)
            }
        }
        .card()
    }

    private var runButton: some View {
        Button {
            Task { await run() }
        } label: {
            Text("Run stress test")
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 4)
        }
        .buttonStyle(.borderedProminent)
        .tint(.pulseGreen)
        .disabled(running)
    }

    private func resultsSection(_ r: StressTestResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Book impact", subtitle: r.scenario.summary)
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Stressed value")
                    Spacer()
                    Text(money(r.totals.stressedValue)).fontWeight(.semibold)
                }
                .font(.subheadline)
                HStack(alignment: .firstTextBaseline) {
                    Text("P&L impact")
                    Spacer()
                    Text(signedMoney(r.totals.pnl))
                        .font(.title2.weight(.bold))
                        .foregroundStyle(pnlColor(r.totals.pnl))
                }
                Text("Current book value \(money(r.totals.baseValue)). Positions the market couldn't price are excluded.")
                    .font(.caption)
                    .foregroundStyle(Color.pulseSecondary)
            }
            .card()
            ForEach(r.positions) { pos in
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(pos.underlying).font(.headline)
                        Text(pos.displayName)
                            .font(.caption)
                            .foregroundStyle(Color.pulseSecondary)
                        if let note = pos.note {
                            Text(note)
                                .font(.caption)
                                .foregroundStyle(Color.pulseTertiary)
                        }
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(signedMoney(pos.pnl))
                            .fontWeight(.semibold)
                            .foregroundStyle(pnlColor(pos.pnl))
                        if let p = pos.pnlPct {
                            Text(pct(p, digits: 1))
                                .font(.caption)
                                .foregroundStyle(pnlColor(pos.pnl))
                        }
                    }
                }
                .card()
            }
            Text("Paper trade only. Stress values are Black-Scholes estimates, not live marks.")
                .font(.caption)
                .foregroundStyle(Color.pulseTertiary)
        }
    }

    private func run() async {
        running = true
        error = nil
        defer { running = false }
        do {
            result = try await APIClient.shared.stressTest(
                priceMovePct: priceMove,
                volJumpPct: volJump,
                daysForward: Int(daysForward)
            )
        } catch {
            self.error = error.localizedDescription
        }
    }
}
