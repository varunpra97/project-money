import SwiftUI
import WebKit

struct AssistantWebView: UIViewRepresentable {
    let screen: String
    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.isOpaque = false
        view.backgroundColor = .black
        view.scrollView.backgroundColor = .black
        view.navigationDelegate = context.coordinator
        return view
    }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func updateUIView(_ view: WKWebView, context: Context) {
        var components = URLComponents(string: AppConfig.baseURL + "/")
        components?.queryItems = [URLQueryItem(name: "assistant", value: "1"), URLQueryItem(name: "chatVersion", value: "3"), URLQueryItem(name: "screen", value: screen)]
        guard let url = components?.url, context.coordinator.loaded != url else { return }
        context.coordinator.loaded = url
        view.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    }
    final class Coordinator: NSObject, WKNavigationDelegate {
        var loaded: URL?
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
            if url.host == URL(string: AppConfig.baseURL)?.host { decisionHandler(.allow) }
            else { decisionHandler(.cancel) }
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            // Constant local fallback: do not interpolate network strings into HTML.
            webView.loadHTMLString("<html><meta name='viewport' content='width=device-width,initial-scale=1'><body style='background:#141517;color:white;font:16px -apple-system;padding:28px'><h2>Connect to your Mac</h2><p>Start the Pulse backend and connect this device to the same network. Close and reopen Assistant to retry.</p></body></html>", baseURL: nil)
        }
    }
}
