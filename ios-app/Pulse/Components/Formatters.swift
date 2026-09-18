import Foundation
import SwiftUI

// MARK: - Money / percent formatting

func money(_ v: Double?, digits: Int = 2) -> String {
    guard let v else { return "—" }
    return v.formatted(.currency(code: "USD").precision(.fractionLength(digits)))
}

func signedMoney(_ v: Double?, digits: Int = 2) -> String {
    guard let v else { return "—" }
    let abs = abs(v).formatted(.currency(code: "USD").precision(.fractionLength(digits)))
    return (v >= 0 ? "+" : "−") + abs
}

func pct(_ v: Double?, digits: Int = 2, signed: Bool = true) -> String {
    guard let v else { return "—" }
    let abs = abs(v).formatted(.number.precision(.fractionLength(digits))) + "%"
    if !signed { return abs }
    return (v >= 0 ? "+" : "−") + abs
}

func pnlColor(_ v: Double?) -> Color {
    guard let v else { return .pulseSecondary }
    if v > 0 { return .pulseGreen }
    if v < 0 { return .pulseRed }
    return .pulseSecondary
}

// MARK: - Dates

private let isoWithFraction: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

private let isoPlain: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
}()

func parseISODate(_ s: String?) -> Date? {
    guard let s, !s.isEmpty else { return nil }
    return isoWithFraction.date(from: s) ?? isoPlain.date(from: s)
}

func relativeString(_ s: String?) -> String {
    guard let d = parseISODate(s) else { return "—" }
    let f = RelativeDateTimeFormatter()
    f.unitsStyle = .short
    return f.localizedString(for: d, relativeTo: Date())
}

/// Short label for the chart scrubber: time for intraday, date otherwise.
func scrubDateLabel(_ date: Date, range: QuoteRange) -> String {
    let f = DateFormatter()
    switch range {
    case .oneDay:
        f.dateStyle = .none
        f.timeStyle = .short
    case .fiveDay:
        f.dateFormat = "E h:mm a"
    default:
        f.dateStyle = .medium
        f.timeStyle = .none
    }
    return f.string(from: date)
}
