import SwiftUI
import Charts

struct PricePoint: Identifiable {
    var id: Date { date }
    let date: Date
    let close: Double
    let open: Double?
    let high: Double?
    let low: Double?
    let volume: Double?
}
func pricePoints(from bars: [Bar]) -> [PricePoint] {
    bars.sorted { $0.t < $1.t }.map {
        PricePoint(date: Date(timeIntervalSince1970: $0.t), close: $0.c,
                   open: $0.o, high: $0.h, low: $0.l, volume: $0.v)
    }
}
func nearestPoint(_ points: [PricePoint], to date: Date) -> PricePoint? {
    points.min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
}
struct ChartStudy: Identifiable {
    var id: Date { date }
    let date: Date
    let sma: Double
    let ema: Double
    let upper: Double
    let lower: Double
}
func chartStudies(_ points: [PricePoint]) -> [ChartStudy] {
    var result: [ChartStudy] = []
    var ema = 0.0
    for i in points.indices {
        guard i >= 19 else { continue }
        let closes = points[(i-19)...i].map(\.close)
        let sma = closes.reduce(0,+) / 20
        ema = i == 19 ? sma : points[i].close * 2 / 21 + ema * 19 / 21
        let variance = closes.reduce(0) { $0 + pow($1 - sma, 2) } / 20
        let deviation = sqrt(variance)
        result.append(ChartStudy(date: points[i].date, sma: sma, ema: ema,
                                 upper: sma + 2 * deviation, lower: sma - 2 * deviation))
    }
    return result
}
struct PriceChart: View {
    let points: [PricePoint]
    let positive: Bool
    @Binding var selectedDate: Date?
    @State private var candles = false
    @State private var indicator = "SMA 20"
    @State private var volume = true
    @State private var count = 100
    @State private var offset = 0
    @State private var expanded = false
    private var visible: [PricePoint] {
        let end = max(0, points.count - min(offset, max(0,points.count-1)))
        return Array(points[max(0,end-count)..<end])
    }
    private var studies: [ChartStudy] {
        guard let first = visible.first?.date, let last = visible.last?.date else { return [] }
        return chartStudies(points).filter { $0.date >= first && $0.date <= last }
    }
    private var selected: PricePoint? {
        if let d = selectedDate { return nearestPoint(visible, to:d) }
        return visible.last
    }
    private var hasOHLC: Bool { visible.allSatisfy { $0.open != nil && $0.high != nil && $0.low != nil } }
    private var xDomain: ClosedRange<Date> {
        let first = visible.first?.date ?? Date()
        let last = visible.last?.date ?? first
        let half = visible.count > 1 ? visible[1].date.timeIntervalSince(first) / 2 : 60
        return first.addingTimeInterval(-half)...last.addingTimeInterval(half)
    }
    private func color(_ p: PricePoint) -> Color { p.close >= (p.open ?? p.close) ? .pulseGreen : .pulseRed }
    /// Robinhood-style line color: green when up, red when down.
    private var lineColor: Color { positive ? Color.pulseGreen : Color.pulseRed }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer()
                Button { expanded.toggle() } label: { Image(systemName: expanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right") }
                    .accessibilityLabel(expanded ? "Hide chart tools" : "Show chart tools")
            }
            if expanded {
                HStack {
                    Picker("Chart type", selection: $candles) {
                        Text("Candles").tag(true)
                        Text("Line").tag(false)
                    }.pickerStyle(.segmented)
                }
                HStack {
                    Picker("Indicator", selection: $indicator) {
                        ForEach(["None", "SMA 20", "EMA 20", "Bollinger 20"], id: \.self) { Text($0) }
                    }.pickerStyle(.menu)
                    Toggle("Volume", isOn: $volume).font(.caption)
                }
                if let p = selected {
                    Text("O \(money(p.open))  H \(money(p.high))  L \(money(p.low))  C \(money(p.close))")
                        .font(.system(size:10, design:.monospaced)).foregroundStyle(Color.pulseSecondary)
                    Text("\(p.date.formatted(date:.abbreviated,time:.shortened)) · Vol \(Int(p.volume ?? 0).formatted())")
                        .font(.caption2).foregroundStyle(Color.pulseSecondary)
                }
            }
            if points.isEmpty { Text("No chart data").foregroundStyle(Color.pulseSecondary) }
            else {
                pricePlot.frame(height: expanded ? 420 : 260)
                if expanded {
                    if volume {
                        Chart(visible) { p in
                            BarMark(x:.value("Time",p.date),y:.value("Volume",p.volume ?? 0))
                                .foregroundStyle(color(p).opacity(0.5))
                        }
                        .chartXScale(domain:xDomain).chartXAxis(.hidden)
                        .chartYAxis { AxisMarks(position:.trailing,values:.automatic(desiredCount:2)) }
                        .frame(height:60)
                    }
                    HStack {
                        Button("←") { offset = min(max(0,points.count-count),offset+max(1,count/3)); selectedDate=nil }
                            .disabled(points.count-offset <= count).accessibilityLabel("Earlier bars")
                        Button("→") { offset=max(0,offset-max(1,count/3)); selectedDate=nil }
                            .disabled(offset==0).accessibilityLabel("Later bars")
                        Spacer()
                        Button("＋") { count=max(20,count*2/3); selectedDate=nil }.disabled(count<=20).accessibilityLabel("Zoom in")
                        Button("−") { count=min(points.count,count*3/2); offset=0; selectedDate=nil }.disabled(count>=points.count).accessibilityLabel("Zoom out")
                        Button("Fit") { count=points.count; offset=0; selectedDate=nil }
                    }.buttonStyle(.bordered)
                    if candles && !hasOHLC { Text("OHLC unavailable. Showing close-price line; refresh to fetch candles.").font(.caption2) }
                    Text(indicator != "None" && studies.isEmpty ? "Indicators need 20 bars." : "Indicators use the selected interval. Bollinger: 20 bars, 2 standard deviations.")
                        .font(.caption2).foregroundStyle(Color.pulseSecondary)
                }
                Text("Yahoo Finance data may be delayed.").font(.caption2).foregroundStyle(Color.pulseSecondary)
            }
        }
        .onChange(of: points.first?.date) { _, _ in offset=0; selectedDate=nil }
    }
    private var pricePlot: some View {
        Chart {
            if !candles || !hasOHLC {
                ForEach(visible) { p in
                    AreaMark(x: .value("Time", p.date), y: .value("Close", p.close))
                        .interpolationMethod(.catmullRom)
                }
                .foregroundStyle(
                    LinearGradient(
                        colors: [lineColor.opacity(0.25), lineColor.opacity(0)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
            }
            ForEach(visible) { p in
                if candles && hasOHLC {
                    RuleMark(x:.value("Time",p.date),yStart:.value("Low",p.low!),yEnd:.value("High",p.high!))
                        .foregroundStyle(color(p))
                    BarMark(x:.value("Time",p.date),yStart:.value("Open",p.open!),yEnd:.value("Close",p.close),width:.ratio(0.65))
                        .foregroundStyle(color(p))
                } else {
                    LineMark(x:.value("Time",p.date),y:.value("Close",p.close),series:.value("Series","Price"))
                        .foregroundStyle(lineColor)
                        .interpolationMethod(.catmullRom)
                        .lineStyle(StrokeStyle(lineWidth: 2))
                }
            }
            if expanded {
                ForEach(studies) { s in
                    if indicator != "None" {
                        LineMark(x:.value("Time",s.date),y:.value("Indicator",indicator == "EMA 20" ? s.ema : s.sma),series:.value("Series","Average"))
                            .foregroundStyle(Color.orange).lineStyle(StrokeStyle(lineWidth:1.5))
                    }
                    if indicator == "Bollinger 20" {
                        LineMark(x:.value("Time",s.date),y:.value("Upper",s.upper),series:.value("Series","Upper"))
                            .foregroundStyle(Color.purple).lineStyle(StrokeStyle(lineWidth:1))
                        LineMark(x:.value("Time",s.date),y:.value("Lower",s.lower),series:.value("Series","Lower"))
                            .foregroundStyle(Color.purple).lineStyle(StrokeStyle(lineWidth:1))
                    }
                }
            }
            if let date = selectedDate, let p = nearestPoint(visible,to:date) {
                RuleMark(x:.value("Selected",p.date)).foregroundStyle(Color.black.opacity(0.5))
                PointMark(x:.value("Selected",p.date), y:.value("Close",p.close))
                    .foregroundStyle(.black)
                    .symbolSize(CGSize(width: 14, height: 14))
            }
        }
        .chartXScale(domain:xDomain)
        .chartYScale(domain:.automatic(includesZero:false))
        .chartYAxis { AxisMarks(position:.trailing,values:.automatic(desiredCount:5)) }
        .chartXAxis { AxisMarks(values:.automatic(desiredCount:3)) }
        .chartXSelection(value:$selectedDate)
    }
}
struct RangePicker: View {
    @Binding var range: QuoteRange
    var body: some View {
        Picker("Range", selection:$range) {
            ForEach(QuoteRange.allCases) { r in Text(r.label).tag(r) }
        }.pickerStyle(.segmented)
    }
}

struct QuoteFreshness: View {
    let quote: QuoteResponse
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("\(quote.source ?? "Price provider") · Market time: \(parseISODate(quote.asOf)?.formatted() ?? "unavailable")")
            if let age = quote.cacheAgeSeconds {
                Text("Server cache age: \(Int(max(0, age)))s\(quote.cacheStale == true || quote.fresh == false ? " · cached / refresh pending" : "")")
            } else if quote.cacheStale == true || quote.fresh == false {
                Text("Cached data · provider refresh pending")
            }
            if let warning = quote.cacheWarning, !warning.isEmpty { Text(warning) }
            Text("Market time can remain unchanged while markets are closed or the provider is delayed.")
        }.font(.caption2).foregroundStyle(Color.pulseSecondary)
    }
}

private struct LiveTick: Decodable {
    let symbol: String
    let price: Double?
    let state: String
    let timestamp: Double?
    let source: String
    let as_of: String?
    var marketDate: Date? { parseISODate(as_of) ?? timestamp.map(Date.init(timeIntervalSince1970:)) }
}
private struct LiveEnvelope: Decodable {
    let quotes: [LiveTick]
    let sent_at: Double
}
struct LiveStockPrice: View {
    let symbol: String
    @Environment(\.scenePhase) private var scenePhase
    @State private var tick: LiveTick?
    @State private var connected = false
    @State private var delivery: Double?
    var body: some View {
        VStack(alignment:.leading,spacing:4) {
            TimelineView(.periodic(from:.now,by:1)) { context in
                let age = tick?.marketDate.map { max(0, context.date.timeIntervalSince($0)) }
                let state = !connected ? "Reconnecting" : tick?.state == "stale" || (age ?? 0) > 90 ? "Last available" : tick?.state == "stream" ? "Streaming" : tick?.state == "polling" ? "Polling fallback" : "Connecting"
                Text("● \(state) · \(symbol) \(money(tick?.price))").font(.caption.weight(.semibold))
                if let date = tick?.marketDate {
                    Text("Market time: \(date.formatted()) · \(Int(age ?? 0))s old")
                        .font(.caption2).foregroundStyle(Color.pulseSecondary)
                }
                if let source = tick?.source { Text(source).font(.caption2).foregroundStyle(Color.pulseSecondary) }
            }
            DisclosureGroup("Latency & improvements") {
                Text("Push delivery: \(delivery.map { String(format: "%.0f ms", $0) } ?? "measuring") (approximate; device clocks affect this). Streaming stock prices use a separate feed from candles and Greeks. Fallback checks every 20 seconds. Provider delays can still apply.")
                Text("Next: Windows-to-phone p50/p95 measurement, synchronized clocks, server placement closer to the provider, and a licensed exchange feed.")
            }.font(.caption2).foregroundStyle(Color.pulseSecondary)
        }
        .task(id: "\(symbol)-\(scenePhase)") {
            guard scenePhase == .active else { return }
            if tick?.symbol != symbol { tick=nil }
            connected=false
            await listen()
        }
    }
    @MainActor private func listen() async {
        var components=URLComponents(string:AppConfig.baseURL + "/api/live/events")
        components?.queryItems=[URLQueryItem(name:"symbols",value:symbol)]
        guard let url=components?.url else { return }
        let configuration=URLSessionConfiguration.ephemeral
        configuration.urlCache=nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest=30
        configuration.timeoutIntervalForResource=86400
        let session=URLSession(configuration:configuration)
        defer { session.invalidateAndCancel(); connected=false }
        while !Task.isCancelled {
            do {
                var request=URLRequest(url:url)
                request.setValue("text/event-stream",forHTTPHeaderField:"Accept")
                let (bytes,response)=try await session.bytes(for:request)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                connected=true
                for try await line in bytes.lines {
                    try Task.checkCancellation()
                    guard line.hasPrefix("data: "),let data=line.dropFirst(6).data(using:.utf8),
                          let payload=try? JSONDecoder().decode(LiveEnvelope.self,from:data) else { continue }
                    tick=payload.quotes.first(where: { $0.symbol == symbol })
                    delivery=max(0,(Date().timeIntervalSince1970-payload.sent_at)*1000)
                    connected=true
                }
            } catch { connected=false }
            connected=false
            if Task.isCancelled { break }
            try? await Task.sleep(for:.seconds(3))
        }
    }
}
