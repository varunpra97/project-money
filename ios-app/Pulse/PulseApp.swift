import SwiftUI

@main
struct PulseApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    @State private var assistantOpen = false
    @State private var selectedTab = "Home"
    @State private var pendingUpgrade: ProductIdea?
    @StateObject private var assistantModel=AssistantModel()
    @Environment(\.scenePhase) private var scenePhase
    /// White in the morning, black at night.
    @State private var scheme: ColorScheme = ContentView.dayScheme()

    /// Light 6:00–18:00, dark otherwise.
    static func dayScheme(for date: Date = Date()) -> ColorScheme {
        let hour = Calendar.current.component(.hour, from: date)
        return (6 <= hour && hour < 18) ? .light : .dark
    }
    var body: some View {
        GeometryReader { geometry in
            HStack(spacing: 0) {
                TabView(selection: $selectedTab) {
                    HomeView().tabItem { Label("Home", systemImage: "chart.line.uptrend.xyaxis") }.tag("Home")
                    PerformanceView().tabItem { Label("Stats", systemImage: "chart.bar.xaxis") }.tag("Stats")
                    NewsView(onUpgrade: { idea in pendingUpgrade=idea; assistantOpen=true }).tabItem { Label("News", systemImage: "newspaper") }.tag("News")
                    DiscoverView().tabItem { Label("Discover", systemImage: "sparkles") }.tag("Discover")
                    SearchView().tabItem { Label("Search", systemImage: "magnifyingglass") }.tag("Search")
                    HistoricalScannersView().tabItem { Label("Scanners", systemImage: "clock.arrow.circlepath") }.tag("Scanners")
                    ActivityView().tabItem { Label("Activity", systemImage: "list.bullet") }.tag("Activity")
                }
                .tint(.pulseGreen)
                .safeAreaInset(edge: .top, spacing: 0) {
                    HStack {
                        Text("Pulse").font(.headline)
                        Spacer()
                    }.padding(.horizontal).padding(.vertical, 8).background(Color.pulseBg)
                }
                if assistantOpen && geometry.size.width >= 850 {
                    NativeAssistantView(screen: selectedTab, upgrade: pendingUpgrade, onUpgradeHandled: { id in if pendingUpgrade?.id == id { pendingUpgrade=nil } }, model: assistantModel).frame(width: 380)
                }
            }
            .sheet(isPresented: Binding(get: { assistantOpen && geometry.size.width < 850 }, set: { if !$0 { assistantOpen = false } })) {
                NavigationStack {
                    NativeAssistantView(screen: selectedTab, upgrade: pendingUpgrade, onUpgradeHandled: { id in if pendingUpgrade?.id == id { pendingUpgrade=nil } }, model: assistantModel)
                        .navigationTitle("Pulse Assistant")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { assistantOpen = false } } }
                }.presentationDetents([.large]).presentationDragIndicator(.visible)
            }
        }
        .preferredColorScheme(scheme)
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { scheme = Self.dayScheme() }
        }
        .onReceive(Timer.publish(every: 300, on: .main, in: .common).autoconnect()) { _ in
            scheme = Self.dayScheme()
        }
    }
}

/// Shown until the user pastes their API URL into Config.swift.
struct SetupView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Pulse")
                    .font(.system(size: 40, weight: .bold))
                Text("One step left")
                    .font(.title2.weight(.semibold))
                Text("Point the app at your Pulse API, then rebuild:")
                    .foregroundStyle(Color.pulseSecondary)
                VStack(alignment: .leading, spacing: 8) {
                    Text("1. In Xcode, open Pulse/Config.swift")
                    Text("2. Set AppConfig.baseURL to your Pulse server URL")
                    Text("3. Press Cmd+R to run again")
                }
                .font(.callout)
                .card()
                Text("The current server is https://varunpc.tail68d841.ts.net/pulse. Keep Tailscale connected on the phone and the Windows server awake.")
                    .font(.footnote)
                    .foregroundStyle(Color.pulseSecondary)
                Spacer()
            }
            .padding()
        }
        .background(Color.pulseBg)
    }
}
