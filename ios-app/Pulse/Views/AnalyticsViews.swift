import SwiftUI
import Charts

struct PerformanceReport: Decodable {
    let period: String
    let as_of: String
    let mode: String?
    let account_value: Double?
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
                    Text(report?.mode == "live" ? "YOUR BROKERAGE ACCOUNT" : "YOUR PAPER PORTFOLIO").font(.caption2.weight(.bold)).foregroundStyle(Color.pulseGreen)
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
                            Text(money(d.pnl)).font(.system(size: 38, weight: .semibold)).heroNumber().foregroundStyle((d.pnl ?? 0) < 0 ? Color.pulseRed : Color.pulseGreen)
                            Text(liveMode(d) ? "Change in account value since tracking began" : (d.pnl == nil ? "Not enough historical marks for this period" : "Realized results + change in unrealized P&L")).font(.caption).foregroundStyle(Color.pulseSecondary)
                            Text("\(d.open_positions) positions open now · \(liveMode(d) ? "Live · Robinhood" : "Paper / saved marks")").font(.caption)
                        }.frame(maxWidth: .infinity, alignment: .leading).card()
                        if liveMode(d) {
                            LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                                metric("Account value", money(d.account_value))
                                metric("Period change", signedMoney(d.pnl))
                                metric("Positions open", String(d.open_positions))
                                metric("Tracking since", shortDate(d.history_since))
                            }
                        } else {
                            LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                                metric("Realized P&L", money(d.realized))
                                metric("Unrealized · now", money(d.unrealized))
                                metric("Opening premiums", money(d.premium))
                                metric("Closed trades", String(d.closed_trades))
                                metric("Win rate", d.win_rate.map { String(format: "%.1f%%", $0) } ?? "—")
                                metric("Profit factor", d.profit_factor.map { String(format: "%.2f", $0) } ?? "—")
                            }
                        }
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(d.curve_label)
                            if d.curve.count > 1 {
                                Chart(d.curve) { point in
                                    LineMark(x: .value("Date", point.date), y: .value("P&L", point.pnl))
                                        .foregroundStyle(Color.pulseGreen)
                                }.frame(height: 180).accessibilityLabel(liveMode(d) ? "Observed account value history" : "Observed paper P&L history")
                            } else {
                                Text("Your history starts here").font(.headline)
                                Text("Snapshots are recorded while the backend runs. A curve appears after the next observation.").font(.caption).foregroundStyle(Color.pulseSecondary)
                            }
                            Text("Observations since \(String(d.history_since.prefix(10))). Gaps connect recorded points; missing periods are not reconstructed.").font(.caption).foregroundStyle(Color.pulseSecondary)
                        }.card()
                        if !liveMode(d) {
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
    private func liveMode(_ d: PerformanceReport) -> Bool { d.mode == "live" }

    private func shortDate(_ iso: String) -> String {
        guard let date = parseISODate(iso) else { return "—" }
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .none
        return f.string(from: date)
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
    var upgradePrompt: String {
        "Implement this approved Pulse product upgrade in the web and iPhone apps where applicable. Inspect existing code, preserve unrelated work, run relevant checks, and report the changes and any deployment steps. Native changes require a signed Xcode build.\n\nUpgrade: \(title)\nScope: \(detail)\nEvaluation: \(measure)"
    }
}

/// One "Build this upgrade" job tracked by the backend (/api/upgrades/*).
/// A Muse builder worker picks up pending jobs, implements them, and deploys.
struct UpgradeJob: Decodable, Identifiable {
    let id: String
    let idea_id: String
    let title: String
    let status: String
    let commit_sha: String?
    let previous_sha: String?
    let error: String?
    let created_at: String?
    let updated_at: String?

    var isActive: Bool {
        ["pending", "building", "undo_requested", "undoing"].contains(status)
    }
}
struct NewsSource: Decodable, Identifiable {
    var id: String { name }
    let name: String
    let fetched: String?
    let stale: Bool
}
struct NewsView: View {
    var onUpgrade: (ProductIdea) -> Void = { _ in }
    @Environment(\.scenePhase) private var scenePhase
    @State private var report: NewsReport?
    @State private var filter = "All"
    @State private var error: String?
    @State private var upgradeJob: UpgradeJob?
    @State private var upgradeError: String?
    @State private var upgradeBusy = false
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
                        Text("Checked \(d.checked_at) · checks the server every minute").font(.caption2).foregroundStyle(Color.pulseSecondary)
                        if d.sources.contains(where: { $0.stale }) {
                            Text("Some sources are unavailable. Older headlines are labeled cached.").font(.caption).foregroundStyle(.orange)
                        }
                        if filter != "Product lab" {
                            if headlines.isEmpty { Text("No headlines available. Pull to refresh.").foregroundStyle(Color.pulseSecondary) }
                            ForEach(headlines) { article in
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("\(article.category.uppercased()) · \(article.source)\(article.stale ? " · cached" : "")").font(.caption2).foregroundStyle(Color.pulseGreen)
                                    if let url = URL(string: article.url) {
                                        Link(destination: url) { Text(article.title + " ↗").font(.title3.weight(.semibold)).foregroundStyle(.primary).multilineTextAlignment(.leading) }
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
                                    Button { onUpgrade(idea) } label: {
                                        HStack { Text(idea.title).font(.title3.weight(.semibold)); Spacer(); Image(systemName: "arrow.up.right") }
                                    }.buttonStyle(.plain).accessibilityLabel("Review upgrade: " + idea.title)
                                    Text(idea.detail).font(.callout)
                                    Divider()
                                    Text("How to evaluate it").font(.caption.weight(.semibold))
                                    Text(idea.measure).font(.caption).foregroundStyle(Color.pulseSecondary)
                                    upgradeControl(for: idea)
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
                .refreshable {
                    await load()
                    await refreshUpgrade()
                }
                .task(id: scenePhase) {
                    guard scenePhase == .active else { return }
                    while !Task.isCancelled {
                        await load()
                        await refreshUpgrade()
                        do { try await Task.sleep(for: .seconds(60)) } catch { return }
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

    // MARK: - Upgrade builder ("Build this upgrade" -> Muse agent -> iPhone)

    private func refreshUpgrade() async {
        do {
            let job = try await APIClient.shared.activeUpgrade()
            if !Task.isCancelled { upgradeJob = job }
        } catch {
            // Keep the last known state; the news feed owns the error surface.
        }
    }

    private func buildUpgrade(_ idea: ProductIdea) async {
        guard !upgradeBusy else { return }
        upgradeBusy = true
        upgradeError = nil
        defer { upgradeBusy = false }
        do {
            upgradeJob = try await APIClient.shared.requestUpgrade(idea: idea)
        } catch {
            upgradeError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func undoUpgrade(_ job: UpgradeJob) async {
        guard !upgradeBusy else { return }
        upgradeBusy = true
        upgradeError = nil
        defer { upgradeBusy = false }
        do {
            upgradeJob = try await APIClient.shared.requestUpgradeUndo(jobId: job.id)
        } catch {
            upgradeError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func upgradeControl(for idea: ProductIdea) -> some View {
        Group {
            if let job = upgradeJob, job.idea_id == idea.id, job.status != "undone" {
                upgradeStatus(job, idea: idea)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    Button("Build this upgrade") {
                        Task { await buildUpgrade(idea) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(upgradeBusy)
                    if jobUndone(for: idea) {
                        Text("Previous build was undone — the app is back to its earlier state.")
                            .font(.caption).foregroundStyle(Color.pulseSecondary)
                    }
                    if let upgradeError {
                        Text(upgradeError).font(.caption).foregroundStyle(Color.pulseRed)
                    }
                }
            }
        }
    }

    private func jobUndone(for idea: ProductIdea) -> Bool {
        upgradeJob?.idea_id == idea.id && upgradeJob?.status == "undone"
    }

    private func upgradeStatus(_ job: UpgradeJob, idea: ProductIdea) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            switch job.status {
            case "pending":
                statusRow("Queued — the builder picks it up within a few minutes.")
            case "building":
                statusRow("Building — implementing the upgrade, then deploying to your iPhone.")
            case "deployed":
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Color.pulseGreen)
                    Text("Deployed to your iPhone")
                        .font(.callout.weight(.semibold))
                }
                Button("Undo this upgrade", role: .destructive) {
                    Task { await undoUpgrade(job) }
                }
                .buttonStyle(.bordered)
                .disabled(upgradeBusy)
                Text("Reverts the upgrade's changes and reinstalls the previous build.")
                    .font(.caption).foregroundStyle(Color.pulseSecondary)
            case "undo_requested", "undoing":
                statusRow("Undoing — reverting the changes and reinstalling the previous build.")
            case "failed":
                Text("Build failed: \(job.error ?? "unknown error")")
                    .font(.callout).foregroundStyle(Color.pulseRed)
                Button("Try again") {
                    Task { await buildUpgrade(idea) }
                }
                .buttonStyle(.bordered)
                .disabled(upgradeBusy)
            default:
                EmptyView()
            }
            if let upgradeError {
                Text(upgradeError).font(.caption).foregroundStyle(Color.pulseRed)
            }
        }
    }

    private func statusRow(_ text: String) -> some View {
        HStack(spacing: 8) {
            ProgressView().scaleEffect(0.8)
            Text(text).font(.callout).foregroundStyle(Color.pulseSecondary)
        }
    }
}

private struct HistoricalConfig: Codable, Identifiable {
    var id:String?
    var name:String
    var symbols:[String]
    var start:String
    var end:String
    var interval:String
    var rule:String
}
private struct HistoricalMatch: Decodable { let symbol:String;let date:String;let close:Double;let indicator:Double }
private struct HistoricalFailure: Decodable { let symbol:String;let error:String }
private struct HistoricalResult: Decodable { let matches:[HistoricalMatch];let total_matches:Int;let errors:[HistoricalFailure];let warnings:[String];let note:String }
private struct HistoricalJob: Decodable {let id:String;let state:String;let result:HistoricalResult?;let error:String?}
struct HistoricalScannersView: View {
    @State private var name="My scanner"
    @State private var symbols="AAPL, MSFT, SPY"
    @State private var from=Date().addingTimeInterval(-90*86400)
    @State private var through=Date()
    @State private var interval="1d"
    @State private var rule="sma20_cross_up"
    @State private var saved:[HistoricalConfig]=[]
    @State private var job:HistoricalJob?
    @State private var error:String?
    @State private var busy=false
    @State private var note=""
    private let rules=[("sma20_cross_up","Cross above SMA 20"),("above_sma200","Close above SMA 200"),("rsi14_oversold","RSI 14 below 30"),("rsi14_overbought","RSI 14 above 70"),("breakout20","Above prior 20-bar high")]
    private static let dateFormat:DateFormatter = {
        let f=DateFormatter();f.locale=Locale(identifier:"en_US_POSIX");f.timeZone=TimeZone(secondsFromGMT:0);f.dateFormat="yyyy-MM-dd";return f
    }()
    private var config:HistoricalConfig { HistoricalConfig(name:name,symbols:symbols.split { $0=="," || $0.isWhitespace }.map {String($0).uppercased()},start:Self.dateFormat.string(from:from),end:Self.dateFormat.string(from:through),interval:interval,rule:rule) }
    var body: some View {
        NavigationStack {
            Form {
                Section { Text("Find technical signals in historical adjusted stock prices. Rules only use bars available at that time; this is not a strategy backtest.").font(.caption).foregroundStyle(.secondary) }
                if !saved.isEmpty {
                    Section("Saved scanners") {
                        Menu("Load configuration") {
                            ForEach(Array(saved.enumerated()),id:\.offset) { _,c in
                                Button(c.name) { name=c.name;symbols=c.symbols.joined(separator:", ");from=Self.dateFormat.date(from:c.start) ?? from;through=Self.dateFormat.date(from:c.end) ?? through;interval=c.interval;rule=c.rule;job=nil }
                            }
                        }
                    }
                }
                Section("Configure") {
                    TextField("Scanner name",text:$name)
                    TextField("Tickers (up to 20)",text:$symbols).textInputAutocapitalization(.characters).autocorrectionDisabled()
                    DatePicker("From",selection:$from,in:...through,displayedComponents:.date)
                    DatePicker("Through",selection:$through,in:from...Date(),displayedComponents:.date)
                    Picker("Timeframe",selection:$interval) { Text("Daily").tag("1d");Text("Weekly").tag("1wk");Text("Monthly").tag("1mo") }
                    Picker("Rule",selection:$rule) { ForEach(rules,id:\.0) {key,label in Text(label).tag(key)} }
                    Button("Run historical scan") { Task {await run()} }.disabled(busy || job?.state=="running")
                    Button("Save configuration") { Task {await save()} }.disabled(busy)
                    if !note.isEmpty {Text(note).font(.caption)}
                }
                if let error { Section {Text(error).foregroundStyle(Color.pulseRed)} }
                if let job {
                    if job.state=="running" {Section {HStack {ProgressView();Text("Scanning historical bars…")}}}
                    if let error=job.error {Section {Text(error).foregroundStyle(Color.pulseRed)}}
                    if let result=job.result {
                        Section("\(result.total_matches) matches") {
                            Text(result.note).font(.caption).foregroundStyle(.secondary)
                            ForEach(result.warnings,id:\.self) {Text($0).font(.caption)}
                            ForEach(Array(result.errors.enumerated()),id:\.offset) { _,e in Text("\(e.symbol): \(e.error)").font(.caption).foregroundStyle(Color.pulseRed) }
                            ForEach(Array(result.matches.prefix(200).enumerated()),id:\.offset) { _,m in
                                HStack { VStack(alignment:.leading) {Text(m.symbol).bold();Text(m.date).font(.caption).foregroundStyle(.secondary)};Spacer();VStack(alignment:.trailing) {Text(money(m.close));Text("Indicator \(m.indicator.formatted(.number.precision(.fractionLength(2))))").font(.caption).foregroundStyle(.secondary)} }
                            }
                            if result.total_matches>200 {Text("Showing the latest 200. Narrow the date range for fewer results.").font(.caption)}
                        }
                    }
                }
            }.navigationTitle("Historical scanners")
                .task {do {saved=try await request("/scanners")}catch {self.error=error.localizedDescription}}
                .task(id:job?.id) {
                    guard let id=job?.id else {return}
                    while !Task.isCancelled && job?.state=="running" {
                        do {try await Task.sleep(for:.seconds(1));let result:HistoricalJob=try await request("/jobs/\(id)");if job?.id==id {job=result}}
                        catch {if !Task.isCancelled {self.error=error.localizedDescription};return}
                    }
                }
        }
    }
    private func request<T:Decodable>(_ path:String,config:HistoricalConfig?=nil) async throws -> T {
        guard let url=URL(string:AppConfig.baseURL+"/api/history"+path) else {throw URLError(.badURL)}
        var r=URLRequest(url:url);r.timeoutInterval=20;r.cachePolicy = .reloadIgnoringLocalCacheData
        r.setValue("1",forHTTPHeaderField:"X-Pulse-Scanner")
        if let config {r.httpMethod="POST";r.setValue("application/json",forHTTPHeaderField:"Content-Type");r.httpBody=try JSONEncoder().encode(config)}
        let (data,response)=try await URLSession.shared.data(for:r)
        guard let http=response as? HTTPURLResponse,(200..<300).contains(http.statusCode) else {
            let detail=(try? JSONSerialization.jsonObject(with:data) as? [String:Any])?["detail"] as? String
            throw NSError(domain:"Scanner",code:1,userInfo:[NSLocalizedDescriptionKey:detail ?? "Check ticker symbols and dates. Maximum 20 tickers and ten years."])
        }
        return try JSONDecoder().decode(T.self,from:data)
    }
    @MainActor private func run() async {busy=true;error=nil;note="";defer {busy=false};do {job=try await request("/run",config:config)}catch {self.error=error.localizedDescription}}
    @MainActor private func save() async {busy=true;error=nil;defer {busy=false};do {let _:HistoricalConfig=try await request("/scanners",config:config);saved=try await request("/scanners");note="Scanner saved on the backend."}catch {self.error=error.localizedDescription}}
}
