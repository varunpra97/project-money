import SwiftUI

// MARK: - Brand

extension Color {
    /// Robinhood green
    static let pulseGreen = Color(red: 0.0, green: 200.0 / 255.0, blue: 5.0 / 255.0)
    /// Robinhood red
    static let pulseRed = Color(red: 1.0, green: 80.0 / 255.0, blue: 0.0)
    static let pulseBg = Color.black
    static let pulseCard = Color(white: 0.09)
    static let pulseSecondary = Color(white: 0.62)
    static let pulseTertiary = Color(white: 0.4)
}

// MARK: - Card container

extension View {
    /// Dark rounded card used across tabs.
    func card() -> some View {
        self
            .padding()
            .background(Color.pulseCard)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

// MARK: - Shared bits

struct SectionHeader: View {
    let title: String
    let subtitle: String?

    init(_ title: String, subtitle: String? = nil) {
        self.title = title
        self.subtitle = subtitle
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.title3.weight(.semibold))
            if let subtitle {
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.pulseSecondary)
            }
        }
        .padding(.top, 8)
    }
}

struct ErrorCard: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "wifi.exclamationmark")
                .font(.title2)
                .foregroundStyle(.pulseSecondary)
            Text(message)
                .font(.callout)
                .foregroundStyle(.pulseSecondary)
                .multilineTextAlignment(.center)
            Button("Try again", action: retry)
                .buttonStyle(.borderedProminent)
                .tint(.pulseGreen)
        }
        .card()
    }
}

/// Small pill badge, e.g. "in 7 days", "⚡ Volatile".
struct Pill: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.16))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}
