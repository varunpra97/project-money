import SwiftUI

@main
struct PulseApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
    }
}

struct ContentView: View {
    @State private var assistantOpen = false
    @State private var selectedTab = "Home"
    var body: some View {
        GeometryReader { geometry in
            HStack(spacing: 0) {
                TabView(selection: $selectedTab) {
                    HomeView().tabItem { Label("Home", systemImage: "chart.line.uptrend.xyaxis") }.tag("Home")
                    PerformanceView().tabItem { Label("Stats", systemImage: "chart.bar.xaxis") }.tag("Stats")
                    NewsView().tabItem { Label("News", systemImage: "newspaper") }.tag("News")
                    DiscoverView().tabItem { Label("Discover", systemImage: "sparkles") }.tag("Discover")
                    SearchView().tabItem { Label("Search", systemImage: "magnifyingglass") }.tag("Search")
                    ActivityView().tabItem { Label("Activity", systemImage: "list.bullet") }.tag("Activity")
                }
                .tint(.pulseGreen)
                .safeAreaInset(edge: .top, spacing: 0) {
                    HStack {
                        Text("Pulse").font(.headline)
                        Spacer()
                        Button { assistantOpen.toggle() } label: { Label("Assistant", systemImage: "sparkle") }
                    }.padding(.horizontal).padding(.vertical, 8).background(Color.pulseBg)
                }
                if assistantOpen && geometry.size.width >= 850 {
                    AssistantWebView(screen: selectedTab).frame(width: 380)
                }
            }
            .sheet(isPresented: Binding(get: { assistantOpen && geometry.size.width < 850 }, set: { if !$0 { assistantOpen = false } })) {
                NavigationStack {
                    AssistantWebView(screen: selectedTab)
                        .navigationTitle("Pulse Assistant")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { assistantOpen = false } } }
                }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
            }
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
                    Text("2. Set AppConfig.baseURL to your API's public URL")
                    Text("3. Press Cmd+R to run again")
                }
                .font(.callout)
                .card()
                Text("The API URL looks like https://something.trycloudflare.com — no trailing slash. It comes from whoever hosts your Pulse backend.")
                    .font(.footnote)
                    .foregroundStyle(Color.pulseSecondary)
                Spacer()
            }
            .padding()
        }
        .background(Color.pulseBg)
    }
}
