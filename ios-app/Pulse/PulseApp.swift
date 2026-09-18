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
    var body: some View {
        if AppConfig.baseURL.isEmpty {
            SetupView()
        } else {
            TabView {
                HomeView()
                    .tabItem {
                        Label("Home", systemImage: "chart.line.uptrend.xyaxis")
                    }
                DiscoverView()
                    .tabItem {
                        Label("Discover", systemImage: "sparkles")
                    }
                SearchView()
                    .tabItem {
                        Label("Search", systemImage: "magnifyingglass")
                    }
                ActivityView()
                    .tabItem {
                        Label("Activity", systemImage: "list.bullet")
                    }
            }
            .tint(.pulseGreen)
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
