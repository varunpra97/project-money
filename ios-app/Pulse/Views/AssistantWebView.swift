import SwiftUI
import WebKit

struct AssistantWebView: UIViewRepresentable {
    let screen: String
    /// Optional pairing code from a deep link / QR handoff.
    var pairCode: String? = nil

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
        var items: [URLQueryItem] = [
            URLQueryItem(name: "assistant", value: "1"),
            URLQueryItem(name: "chatVersion", value: "3"),
            URLQueryItem(name: "screen", value: screen),
        ]
        // Prefer explicit pairCode; otherwise keep an existing ?pair= on the loaded URL.
        var pair = pairCode
        if pair == nil, let current = view.url, let cur = URLComponents(url: current, resolvingAgainstBaseURL: false) {
            pair = cur.queryItems?.first(where: { $0.name == "pair" })?.value
        }
        if let pair, !pair.isEmpty {
            items.append(URLQueryItem(name: "pair", value: pair))
        }
        components?.queryItems = items
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

// Native controls avoid WKWebView focus/gesture problems inside a resizable sheet.
import Security

private struct AssistantMessage: Decodable, Identifiable { let id: String; let role: String; let text: String }
private struct AssistantApproval: Decodable, Identifiable { let id: String; let detail: String; let reason: String? }
private struct AssistantChat: Decodable, Identifiable {
    let id: String
    let title: String
    let messages: [AssistantMessage]
    let busy: Bool
    let error: String?
    let activity: String
    let diff: String
    let approvals: [AssistantApproval]
}
private struct AssistantStatus: Decodable { let ready: Bool; let message: String }
private struct AssistantAccess: Decodable { let token: String }
private struct AssistantChatSummary: Decodable, Identifiable { let id: String; let title: String; let busy: Bool }
private struct AssistantOK: Decodable { let ok: Bool }

private enum AssistantCredential {
    static var account: String { AppConfig.baseURL }
    static var query: [String:Any] { [kSecClass as String:kSecClassGenericPassword,
        kSecAttrService as String:"PulseAssistant", kSecAttrAccount as String:account] }
    static func read() -> String {
        var q=query; q[kSecReturnData as String]=true; q[kSecMatchLimit as String]=kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary,&result)==errSecSuccess,let data=result as? Data else { return "" }
        return String(data:data,encoding:.utf8) ?? ""
    }
    static func write(_ token:String) throws {
        if token.isEmpty { SecItemDelete(query as CFDictionary);return }
        let data=Data(token.utf8)
        let result=SecItemUpdate(query as CFDictionary,[kSecValueData as String:data] as CFDictionary)
        if result==errSecItemNotFound {
            var q=query;q[kSecValueData as String]=data
            q[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(q as CFDictionary,nil)==errSecSuccess else { throw URLError(.cannotWriteToFile) }
        } else if result != errSecSuccess { throw URLError(.cannotWriteToFile) }
    }
}

@MainActor private final class AssistantModel: ObservableObject {
    @Published var token=AssistantCredential.read()
    @Published var pairingCode=""
    @Published var input=""
    @Published var mode="ask"
    @Published var status:AssistantStatus?
    @Published var chat:AssistantChat?
    @Published var chats:[AssistantChatSummary]=[]
    @Published var selectedID=""
    @Published var error:String?
    @Published var working=false
    private let session:URLSession = {
        let config=URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest=25
        return URLSession(configuration:config)
    }()
    func request<T:Decodable>(_ path:String, body:[String:Any]?=nil, auth:String?=nil) async throws -> T {
        guard let url=URL(string:AppConfig.baseURL+"/api/assistant"+path) else { throw URLError(.badURL) }
        var req=URLRequest(url:url);req.cachePolicy = .reloadIgnoringLocalCacheData
        req.setValue("1",forHTTPHeaderField:"X-Pulse-Assistant")
        req.setValue("application/json",forHTTPHeaderField:"Content-Type")
        req.setValue("Bearer \(auth ?? token)",forHTTPHeaderField:"Authorization")
        if let body { req.httpMethod="POST";req.httpBody=try JSONSerialization.data(withJSONObject:body) }
        let (data,response)=try await session.data(for:req)
        guard let http=response as? HTTPURLResponse,(200..<300).contains(http.statusCode) else {
            if (response as? HTTPURLResponse)?.statusCode==401 { token="";try? AssistantCredential.write("");status=nil }
            let detail=(try? JSONSerialization.jsonObject(with:data) as? [String:Any])?["detail"] as? String
            throw NSError(domain:"PulseAssistant",code:(response as? HTTPURLResponse)?.statusCode ?? 0,
                userInfo:[NSLocalizedDescriptionKey:detail ?? "Cannot reach the assistant. Check the server connection."])
        }
        return try JSONDecoder().decode(T.self,from:data)
    }
    func connect() async {
        error=nil
        do {
            #if targetEnvironment(simulator)
            if token.isEmpty {
                let access:AssistantAccess=try await request("/bootstrap")
                try AssistantCredential.write(access.token);token=access.token
            }
            #endif
            guard !token.isEmpty else { return }
            status=try await request("/status")
            chats=try await request("/chats")
        } catch { if !Task.isCancelled { self.error=error.localizedDescription } }
    }
    func pair() async {
        guard !working else { return };working=true;defer {working=false};error=nil
        do {
            let access:AssistantAccess=try await request("/pair",body:["code":pairingCode],auth:"")
            try AssistantCredential.write(access.token);token=access.token;pairingCode=""
            await connect()
        } catch { self.error=error.localizedDescription }
    }
    func select(_ id:String) async {
        selectedID=id;chat=nil;error=nil
        guard !id.isEmpty else { return }
        do { let result:AssistantChat=try await request("/chats/\(id)");if selectedID==id { chat=result } }
        catch { self.error=error.localizedDescription }
    }
    func poll() async {
        let id=selectedID;guard !id.isEmpty,!token.isEmpty else { return }
        do { let result:AssistantChat=try await request("/chats/\(id)");if selectedID==id { chat=result } }
        catch { if !Task.isCancelled { self.error=error.localizedDescription } }
    }
    func send(screen:String) async {
        let text=input.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !text.isEmpty,!working,chat?.busy != true,status?.ready == true else { return }
        working=true;defer {working=false};error=nil
        do {
            var body:[String:Any]=["text":text,"mode":mode,"screen":screen]
            if !selectedID.isEmpty {body["chat_id"]=selectedID}
            let result:AssistantChat=try await request("/messages",body:body)
            chat=result;selectedID=result.id;input="";chats=try await request("/chats")
        } catch { self.error=error.localizedDescription }
    }
    func action(_ path:String, body:[String:Any]) async {
        guard !working else {return};working=true;defer {working=false}
        do { let _:AssistantOK=try await request(path,body:body);await poll() }
        catch { self.error=error.localizedDescription }
    }
}

struct NativeAssistantView: View {
    let screen:String
    @StateObject private var model=AssistantModel()
    @Environment(\.scenePhase) private var scenePhase
    @FocusState private var focused:Bool
    var body: some View {
        VStack(spacing:0) {
            HStack {
                Image(systemName:"sparkles").foregroundStyle(Color.pulseGreen)
                VStack(alignment:.leading) {
                    Text(model.status?.ready == true ? "Connected · Codex" : "Connect to your server").font(.caption.weight(.semibold))
                    Text("Viewing \(screen)").font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    Button("New conversation") { Task { await model.select("") } }
                    ForEach(model.chats) { c in Button(c.title) { Task { await model.select(c.id) } } }
                } label: { Image(systemName:"bubble.left.and.bubble.right") }.accessibilityLabel("Conversations")
                Button { Task { await model.select("") } } label: { Image(systemName:"plus") }.accessibilityLabel("New conversation")
            }.padding()
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment:.leading,spacing:18) {
                        if model.token.isEmpty { pairing }
                        else if model.status?.ready != true {
                            Text(model.status?.message ?? "Checking the assistant connection…")
                            Button("Check connection") { Task { await model.connect() } }.buttonStyle(.bordered)
                        }
                        if let error=model.error { Text(error).font(.callout).foregroundStyle(Color.pulseRed).accessibilityIdentifier("assistantError") }
                        if let error=model.chat?.error { Text(error).font(.callout).foregroundStyle(Color.pulseRed) }
                        if model.chat?.messages.isEmpty != false && model.status?.ready == true {
                            Text("Ask about Pulse or describe a code change.").font(.title3.weight(.semibold))
                            Text("Choose Edit app to modify the repository. Changes to the native app still need an Xcode rebuild.").font(.callout).foregroundStyle(.secondary)
                        }
                        ForEach(model.chat?.messages ?? []) { message in
                            VStack(alignment:.leading,spacing:6) {
                                Text(message.role=="user" ? "You" : "Pulse Assistant").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                Text(message.text.isEmpty ? "…" : message.text).textSelection(.enabled)
                            }.padding(12).frame(maxWidth:.infinity,alignment:.leading)
                                .background(message.role=="user" ? Color.pulseCard : Color.clear).clipShape(RoundedRectangle(cornerRadius:12))
                        }
                        if model.chat?.busy == true { HStack {ProgressView();Text(model.chat?.activity ?? "Working…").font(.caption)} }
                        if let diff=model.chat?.diff,!diff.isEmpty { DisclosureGroup("Source changes") { Text(diff).font(.system(.caption,design:.monospaced)).textSelection(.enabled) } }
                        ForEach(model.chat?.approvals ?? []) { approval in
                            VStack(alignment:.leading,spacing:10) {
                                Text("Permission requested").font(.headline)
                                Text(approval.detail).font(.caption).textSelection(.enabled)
                                HStack {
                                    Button("Approve once") { Task { await decide(approval.id,true) } }
                                    Button("Decline",role:.destructive) { Task { await decide(approval.id,false) } }
                                }.buttonStyle(.bordered).disabled(model.working)
                            }.padding().background(Color.pulseCard).clipShape(RoundedRectangle(cornerRadius:12))
                        }
                        Color.clear.frame(height:1).id("bottom")
                    }.padding().frame(maxWidth:.infinity,alignment:.leading)
                }.scrollDismissesKeyboard(.interactively)
                    .onChange(of:model.chat?.messages.last?.text) { _,_ in proxy.scrollTo("bottom",anchor:.bottom) }
            }
            Divider()
            VStack(spacing:8) {
                HStack {
                    Picker("Assistant mode",selection:$model.mode) {
                        Text("Ask").tag("ask");Text("Edit app").tag("edit")
                    }.pickerStyle(.segmented).disabled(model.chat?.busy == true || model.working)
                    if model.chat?.busy == true,let id=model.chat?.id {
                        Button("Stop") { Task { await model.action("/chats/\(id)/stop",body:[:]) } }
                    }
                }
                TextField("Message assistant…",text:$model.input,axis:.vertical)
                    .lineLimit(2...5).padding(12).background(Color.pulseCard).clipShape(RoundedRectangle(cornerRadius:10))
                    .focused($focused).accessibilityIdentifier("assistantMessage")
                HStack {
                    Text(model.token.isEmpty ? "Pair this device to send messages." : "App context and messages are sent to OpenAI.")
                        .font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Button { focused=false;Task { await model.send(screen:screen) } } label: { Label("Send",systemImage:"arrow.up") }
                        .buttonStyle(.borderedProminent).tint(Color.pulseGreen)
                        .disabled(model.status?.ready != true || model.input.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || model.working || model.chat?.busy == true)
                        .accessibilityIdentifier("assistantSend")
                }
            }.padding().background(Color.pulseBg)
        }.background(Color.pulseBg)
            .task(id:scenePhase) {
                guard scenePhase == .active else {return}
                await model.connect()
                while !Task.isCancelled {
                    await model.poll()
                    do {try await Task.sleep(for:.seconds(1))} catch {return}
                }
            }
    }
    private var pairing: some View {
        VStack(alignment:.leading,spacing:12) {
            Text("Pair with your server").font(.title2.weight(.semibold))
            Text("Open Pulse Assistant on your Mac or Windows server's localhost page. Enter its 8-digit pairing code here.").foregroundStyle(.secondary)
            TextField("8-digit pairing code",text:$model.pairingCode)
                .keyboardType(.numberPad).textContentType(.oneTimeCode).textFieldStyle(.roundedBorder)
                .onChange(of:model.pairingCode) { _,value in model.pairingCode=String(value.filter(\.isNumber).prefix(8)) }
                .accessibilityIdentifier("assistantPairCode")
            Button(model.working ? "Pairing…" : "Pair device") { focused=false;Task {await model.pair()} }
                .buttonStyle(.borderedProminent).tint(Color.pulseGreen)
                .disabled(model.pairingCode.count != 8 || model.working).accessibilityIdentifier("assistantPair")
        }
    }
    private func decide(_ id:String,_ approve:Bool) async {
        guard let chatID=model.chat?.id else {return}
        await model.action("/chats/\(chatID)/approvals/\(id)",body:["approve":approve])
    }
}
