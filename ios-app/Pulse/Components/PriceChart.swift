import SwiftUI
import Charts

/// A point on the price chart.
struct PricePoint: Identifiable {
    let id = UUID()
    let date: Date
    let close: Double
}

func pricePoints(from bars: [Bar]) -> [PricePoint] {
    bars
        .sorted { $0.t < $1.t }
        .map { PricePoint(date: Date(timeIntervalSince1970: $0.t), close: $0.c) }
}

func nearestPoint(_ points: [PricePoint], to date: Date) -> PricePoint? {
    points.min(by: {
        abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
    })
}

/// Robinhood-style line chart with drag-to-scrub crosshair.
/// The parent owns `selectedDate` so it can mirror the scrubbed value in the header.
struct PriceChart: View {
    let points: [PricePoint]
    let positive: Bool
    @Binding var selectedDate: Date?

    private var selectedPoint: PricePoint? {
        guard let d = selectedDate else { return nil }
        return nearestPoint(points, to: d)
    }

    var body: some View {
        Group {
            if points.isEmpty {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.pulseCard)
                    .frame(height: 220)
                    .overlay {
                        Text("No chart data")
                            .font(.callout)
                            .foregroundStyle(.pulseSecondary)
                    }
            } else {
                Chart(points) { p in
                    LineMark(
                        x: .value("Time", p.date),
                        y: .value("Price", p.close)
                    )
                    .foregroundStyle(positive ? Color.pulseGreen : Color.pulseRed)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                    .interpolationMethod(.catmullRom)

                    if let s = selectedPoint {
                        RuleMark(x: .value("Time", s.date))
                            .foregroundStyle(Color.white.opacity(0.45))
                            .lineStyle(StrokeStyle(lineWidth: 1))
                        PointMark(
                            x: .value("Time", s.date),
                            y: .value("Price", s.close)
                        )
                        .foregroundStyle(Color.white)
                        .symbolSize(70)
                    }
                }
                .chartXSelection(value: $selectedDate)
                .chartYAxis(.hidden)
                .chartXAxis(.hidden)
                .chartYScale(domain: .automatic(includesZero: false))
                .frame(height: 220)
            }
        }
    }
}

/// Segmented 1D / 1W / 1M / 3M / 1Y range picker.
struct RangePicker: View {
    @Binding var range: QuoteRange

    var body: some View {
        Picker("Range", selection: $range) {
            ForEach(QuoteRange.allCases) { r in
                Text(r.label).tag(r)
            }
        }
        .pickerStyle(.segmented)
    }
}
