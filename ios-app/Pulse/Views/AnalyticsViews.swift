import SwiftUI
import Charts

struct PerformanceReport: Decodable {
    let period: String
    let as_of: String
    let pnl: Double?
    let realized: Double
    let unrealized: Double
    let closed_trades: Int
    let win_rate: Double?
    let average_win: Double?
    let average_loss: Double?
    let best_trade: Double?
    let worst_trade: Double?
    let profit_factor: Double?
    let open_positions: Int
    let premium: Double
    let history_since: String
    let curve: [PerformancePoint]
    let curve_label: String
    let strategies: [StrategyResult]
    let notes: [String]
}
struct PerformancePoint: Decodable, Identifiable {
    var id: String { ts }
    let ts: String
    let pnl: Double
    var date: Date {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: ts) ?? ISO8601DateFormatter().date(from: ts) ?? .distantPast
    }
}
struct StrategyResult: Decodable, Identifiable {
    var id: String { strategy }
    let strategy: String
    let trades: Int
    let realized: Double
}

struct PerformanceView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var period = "lifetime"
    @State private var report: PerformanceReport?
    @State private var error: String?
    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("YOUR PAPER PORTFOLIO").font(.caption2.weight(.bold)).foregroundStyle(Color.pulseGreen)
                    Picker("Period", selection: $period) {
                        Text("Lifetime").tag("lifetime")
                        Text("1 week").tag("week")
                        Text("1 month").tag("month")
                        Text("Quarter").tag("quarter")
                    }.pickerStyle(.segmented)
                    if let error { ErrorCard(message: error) { Task { await load() } } }
                    if let d = report {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(period == "lifetime" ? "Lifetime total P&L" : "Period total P&L").foregroundStyle(Color.pulseSecondary)
                            Text(money(d.pnl)).font(.system(size: 38, weight: .semibold)).foregroundStyle((d.pnl ?? 0) < 0 ? Color.pulseRed : Color.pulseGreen)
                            Text(d.pnl == nil ? "Not enough historical marks for this period" : "Realized results + change in unrealized P&L").font(.caption).foregroundStyle(Color.pulseSecondary)
                            Text("\(d.open_positions) positions open now · Paper / saved marks").font(.caption)
                        }.frame(maxWidth: .infinity, alignment: .leading).card()
                        LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                            metric("Realized P&L", money(d.realized))
                            metric("Unrealized · now", money(d.unrealized))
                            metric("Opening premiums", money(d.premium))
                            metric("Closed trades", String(d.closed_trades))
                            metric("Win rate", d.win_rate.map { String(format: "%.1f%%", $0) } ?? "—")
                            metric("Profit factor", d.profit_factor.map { String(format: "%.2f", $0) } ?? "—")
                        }
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(d.curve_label)
                            if d.curve.count > 1 {
                                Chart(d.curve) { point in
                                    LineMark(x: .value("Date", point.date), y: .value("P&L", point.pnl))
                                        .foregroundStyle(Color.pulseGreen)
                                }.frame(height: 180).accessibilityLabel("Observed paper P&L history")
                            } else {
                                Text("Your history starts here").font(.headline)
                                Text("Snapshots are recorded while the backend runs. A curve appears after the next observation.").font(.caption).foregroundStyle(Color.pulseSecondary)
                            }
                            Text("Observations since \(String(d.history_since.prefix(10))). Gaps connect recorded points; missing periods are not reconstructed.").font(.caption).foregroundStyle(Color.pulseSecondary)
                        }.card()
                        SectionHeader("Trade quality")
                        LazyVGrid(columns: columns, spacing: 12) {
                            metric("Average winner", money(d.average_win))
                            metric("Average loser", money(d.average_loss))
                            metric("Best close", money(d.best_trade))
                            metric("Worst close", money(d.worst_trade))
                        }
                        Text("Based on recorded closes in this window. Flat closes count toward win rate; profit factor requires a losing trade. Premiums are receipts, not profit.").font(.caption).foregroundStyle(Color.pulseSecondary)
                        SectionHeader("Results by strategy")
                        if d.strategies.isEmpty { Text("No dated closed trades in this period yet.").font(.callout).foregroundStyle(Color.pulseSecondary) }
                        ForEach(d.strategies) { s in
                            HStack { VStack(alignment: .leading) { Text(s.strategy); Text("\(s.trades) closed trades").font(.caption).foregroundStyle(Color.pulseSecondary) }; Spacer(); Text(money(s.realized)) }.card()
                        }
                        DisclosureGroup("About these numbers") {
                            VStack(alignment: .leading, spacing: 10) {
                                ForEach(d.notes, id: \.self) { Text($0) }
                                Text("Updated \(d.as_of)")
                            }.font(.caption).foregroundStyle(Color.pulseSecondary).padding(.top, 10)
                        }
                    } else if error == nil { ProgressView("Loading performance…").frame(maxWidth: .infinity).padding(40) }
                }.padding()
            }
            .background(Color.pulseBg).navigationTitle("Performance")
            .refreshable { await load() }
            .task(id: "\(period)-\(scenePhase)") {
                guard scenePhase == .active else { return }
                await load()
            }
        }
    }
    private func metric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label).font(.caption).foregroundStyle(Color.pulseSecondary)
            Text(value).font(.title3.weight(.semibold)).minimumScaleFactor(0.7).lineLimit(1)
        }.frame(maxWidth: .infinity, alignment: .leading).card()
    }
    private func load() async {
        let requested = period
        if report?.period != requested { report = nil }
        error = nil
        do {
            let value: PerformanceReport = try await APIClient.shared.get("/api/performance", query: ["period": requested], ttl: 0)
            guard !Task.isCancelled, period == requested else { return }
            report = value
        } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
    }
}

struct NewsReport: Decodable {
    let checked_at: String
    let items: [NewsHeadline]
    let ideas: [ProductIdea]
    let sources: [NewsSource]
}
struct NewsHeadline: Decodable, Identifiable {
    let id: String
    let title: String
    let url: String
    let source: String
    let category: String
    let published: String?
    let stale: Bool
}
struct ProductIdea: Decodable, Identifiable {
    let id: String
    let title: String
    let detail: String
    let measure: String
    let effort: String
    let related_title: String?
    let related_url: String?
}
struct NewsSource: Decodable, Identifiable {
    var id: String { name }
    let name: String
    let fetched: String?
    let stale: Bool
}
struct NewsView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var report: NewsReport?
    @State private var filter = "All"
    @State private var error: String?
    private var headlines: [NewsHeadline] {
        report?.items.filter { filter == "All" || $0.category == filter } ?? []
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Market context, options updates, and ways to make Pulse better.").font(.callout).foregroundStyle(Color.pulseSecondary)
                    Picker("Feed category", selection: $filter) {
                        ForEach(["All", "Options", "Markets", "Product lab"], id: \.self) { Text($0).tag($0) }
                    }.pickerStyle(.segmented)
                    if let error { ErrorCard(message: error) { Task { await load() } } }
                    if let d = report {
                        Text("Checked \(d.checked_at) · refreshes every 10 min").font(.caption2).foregroundStyle(Color.pulseSecondary)
                        if d.sources.contains(where: { $0.stale }) {
                            Text("Some sources are unavailable. Older headlines are labeled cached.").font(.caption).foregroundStyle(.orange)
                        }
                        if filter != "Product lab" {
                            if headlines.isEmpty { Text("No headlines available. Pull to refresh.").foregroundStyle(Color.pulseSecondary) }
                            ForEach(headlines) { article in
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("\(article.category.uppercased()) · \(article.source)\(article.stale ? " · cached" : "")").font(.caption2).foregroundStyle(Color.pulseGreen)
                                    if let url = URL(string: article.url) {
                                        Link(destination: url) { Text(article.title + " ↗").font(.title3.weight(.semibold)).foregroundStyle(.white).multilineTextAlignment(.leading) }
                                    }
                                    Text(article.published ?? "Publication date unavailable").font(.caption2).foregroundStyle(Color.pulseSecondary)
                                }.frame(maxWidth: .infinity, alignment: .leading).card()
                            }
                        }
                        if filter == "All" || filter == "Product lab" {
                            SectionHeader("Product lab", subtitle: "Editorial ideas for improving Pulse — not news or trading recommendations.")
                            ForEach(d.ideas) { idea in
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("PRODUCT IDEA · \(idea.effort.uppercased()) EFFORT").font(.caption2).foregroundStyle(Color.pulseGreen)
                                    Text(idea.title).font(.title3.weight(.semibold))
                                    Text(idea.detail).font(.callout)
                                    Divider()
                                    Text("How to evaluate it").font(.caption.weight(.semibold))
                                    Text(idea.measure).font(.caption).foregroundStyle(Color.pulseSecondary)
                                    if let raw = idea.related_url, let url = URL(string: raw) { Link("Related: " + (idea.related_title ?? "Read source"), destination: url).font(.caption) }
                                }.frame(maxWidth: .infinity, alignment: .leading).card()
                            }
                        }
                        DisclosureGroup("Sources & freshness") {
                            ForEach(d.sources) { source in
                                Text("\(source.name) · \(source.fetched ?? "Not yet fetched")\(source.stale ? " · cached / unavailable" : "")").font(.caption).padding(.vertical, 5)
                            }
                            Text("Publisher headlines and dates. Product ideas use curated themes matched to headlines.").font(.caption)
                        }
                    } else if error == nil { ProgressView("Fetching headlines…").frame(maxWidth: .infinity).padding(40) }
                }.padding()
            }.background(Color.pulseBg).navigationTitle("News & ideas")
                .refreshable { await load() }
                .task(id: scenePhase) {
                    guard scenePhase == .active else { return }
                    while !Task.isCancelled {
                        await load()
                        do { try await Task.sleep(for: .seconds(600)) } catch { return }
                    }
                }
        }
    }
    private func load() async {
        error = nil
        do {
            let value: NewsReport = try await APIClient.shared.get("/api/news", query: ["refresh":"true"], ttl: 0)
            if !Task.isCancelled { report = value }
        } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
    }
}
