import SwiftUI

struct ActivityView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var items: [ActivityItem] = []
    @State private var summary: PortfolioSummary?
    @State private var error: String?
    @State private var loading = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    statsRow
                    SectionHeader("Activity", subtitle: "Fills and closed positions, newest first")
                    if loading && items.isEmpty {
                        ForEach(0..<4, id: \.self) { _ in
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.pulseCard)
                                .frame(height: 64)
                                .redacted(reason: .placeholder)
                        }
                    } else if let error, items.isEmpty {
                        ErrorCard(message: error) {
                            Task { await load() }
                        }
                    } else if items.isEmpty {
                        Text("No activity yet.")
                            .font(.callout)
                            .foregroundStyle(Color.pulseSecondary)
                            .card()
                    } else {
                        ForEach(items) { item in
                            activityRow(item)
                        }
                    }
                }
                .padding()
            }
            .background(Color.pulseBg)
            .navigationTitle("Activity")
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
    }

    // MARK: - Stats

    private var statsRow: some View {
        HStack(spacing: 10) {
            statCard("Buying power", money(summary?.buyingPower, digits: 0))
            statCard("Total P&L", signedMoney(summary?.totalPnl, digits: 0),
                     color: pnlColor(summary?.totalPnl))
            statCard("Open", summary.map { "\($0.openPositions)" } ?? "—")
        }
        .redacted(reason: loading && summary == nil ? .placeholder : [])
    }

    private func statCard(_ label: String, _ value: String, color: Color = .white) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(Color.pulseSecondary)
            Text(value)
                .font(.title3.weight(.semibold))
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
    }

    // MARK: - Feed

    private func activityRow(_ item: ActivityItem) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon(for: item.kind))
                .font(.title3)
                .foregroundStyle(color(for: item.kind))
                .frame(width: 32)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.text)
                    .font(.callout)
                    .lineLimit(2)
                Text(relativeString(item.ts))
                    .font(.caption)
                    .foregroundStyle(Color.pulseSecondary)
            }
            Spacer()
            if let amt = item.amount {
                Text(signedMoney(amt))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(pnlColor(amt))
            }
        }
        .card()
    }

    private func icon(for kind: String) -> String {
        switch kind.lowercased() {
        case "fill": return "arrow.left.arrow.right.circle"
        case "close": return "xmark.circle"
        case "open": return "plus.circle"
        default: return "circle"
        }
    }

    private func color(for kind: String) -> Color {
        switch kind.lowercased() {
        case "fill": return .blue
        case "close": return .pulseSecondary
        case "open": return .pulseGreen
        default: return .pulseSecondary
        }
    }

    // MARK: - Loading

    private func load() async {
        loading = true
        error = nil
        do {
            async let a = APIClient.shared.activity()
            async let s = APIClient.shared.summary()
            let (aa, ss) = try await (a, s)
            items = aa
            summary = ss
        } catch {
            self.error = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        loading = false
    }
}
