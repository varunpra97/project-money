import SwiftUI

// MARK: - Brand

extension Color {
    /// Robinhood green
    static let pulseGreen = Color(red: 0.0, green: 200.0 / 255.0, blue: 5.0 / 255.0)
    /// Robinhood red
    static let pulseRed = Color(red: 1.0, green: 80.0 / 255.0, blue: 0.0)
    static let pulseBg = Color(white: 0.28)
    static let pulseCard = Color(white: 0.36)
    static let pulseSecondary = Color(white: 0.65)
    static let pulseTertiary = Color(white: 0.45)
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
                    .foregroundStyle(Color.pulseSecondary)
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
                .foregroundStyle(Color.pulseSecondary)
            Text(message)
                .font(.callout)
                .foregroundStyle(Color.pulseSecondary)
                .multilineTextAlignment(.center)
            Button("Try again", action: retry)
                .buttonStyle(.borderedProminent)
                .tint(.pulseGreen)
        }
        .card()
    }
}

/// Small pill badge, e.g. "in 7 days".
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

// MARK: - Shimmer loading effect

/// Animated sheen that sweeps across skeleton placeholders.
/// Apply after `.redacted(reason: .placeholder)`, e.g. `.redacted(reason: .placeholder).shimmer()`.
struct ShimmerModifier: ViewModifier {
    @State private var sweep: CGFloat = -1.2

    func body(content: Content) -> some View {
        content
            .overlay {
                GeometryReader { geo in
                    LinearGradient(
                        colors: [.clear, .white.opacity(0.14), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: geo.size.width * 0.45)
                    .offset(x: sweep * geo.size.width)
                    .blendMode(.screen)
                }
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .allowsHitTesting(false)
            }
            .onAppear {
                withAnimation(.linear(duration: 1.3).repeatForever(autoreverses: false)) {
                    sweep = 1.2
                }
            }
    }
}

extension View {
    /// Robinhood-style shimmer sweep for loading skeletons.
    func shimmer() -> some View {
        modifier(ShimmerModifier())
    }

    /// Hero number styling: tabular digits that roll when the value changes.
    func heroNumber() -> some View {
        self
            .monospacedDigit()
            .contentTransition(.numericText())
    }
}
