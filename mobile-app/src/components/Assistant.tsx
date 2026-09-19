import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

type Message = { id: string; role: string; text: string };
type Approval = { id: string; kind: string; detail: string; reason?: string; cwd?: string };
type Chat = {
  id: string;
  title: string;
  messages: Message[];
  busy: boolean;
  error: string | null;
  activity: string;
  diff: string;
  approvals: Approval[];
  changes: unknown[];
};
type Status = { ready: boolean; message: string; provider: string; context: string[] };
type Bootstrap = {
  token: string;
  pairing_code: string;
  expires_at: number;
  pair_url?: string | null;
  public_host?: string | null;
};

const base = () => (location.pathname.startsWith("/pulse") ? "/pulse" : "");

function stored(key: string) {
  try {
    return localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore quota / private mode */
  }
}

function isLocalHost(hostname = location.hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

/** Build a scannable pair URL for phones on the same LAN. */
function buildPairUrl(code: string, hint?: string | null) {
  if (hint) return hint;
  const origin = location.origin;
  const b = base();
  const path = b ? `${b}/` : "/";
  return `${origin}${path}?assistant=1&pair=${encodeURIComponent(code)}`;
}

function LocalPairQR({ value }: { value: string }) {
  const [image, setImage] = useState("");
  useEffect(() => {
    let active = true;
    QRCode.toDataURL(value, { width: 200, margin: 2, errorCorrectionLevel: "M" })
      .then(url => { if (active) setImage(url); }).catch(() => { if (active) setImage(""); });
    return () => { active = false; };
  }, [value]);
  return image ? <img className="pair-qr" src={image} width={160} height={160} alt="QR code to pair this Pulse assistant" /> : null;
}

function stripPairFromUrl() {
  try {
    const url = new URL(location.href);
    if (!url.searchParams.has("pair")) return;
    url.searchParams.delete("pair");
    const qs = url.searchParams.toString();
    history.replaceState(null, "", url.pathname + (qs ? `?${qs}` : "") + url.hash);
  } catch {
    /* ignore */
  }
}

export default function Assistant({
  screen,
  onClose,
  standalone = false,
}: {
  screen: string;
  onClose?: () => void;
  standalone?: boolean;
}) {
  const [token, setToken] = useState(() => stored("pulse-assistant-token"));
  const [pairCode, setPairCode] = useState("");
  const [displayCode, setDisplayCode] = useState("");
  const [pairLink, setPairLink] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [chat, setChat] = useState<Chat | null>(null);
  const [chatID, setChatID] = useState(() => stored("pulse-assistant-chat"));
  const [chats, setChats] = useState<{ id: string; title: string; busy: boolean }[]>([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("ask");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [checking, setChecking] = useState(false);
  const [acting, setActing] = useState(false);
  const [autoPairing, setAutoPairing] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const autoPaired = useRef(false);

  async function api(path: string, body?: unknown, auth = token) {
    const response = await fetch(base() + "/api/assistant" + path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "X-Pulse-Assistant": "1",
        "Content-Type": "application/json",
        ...(auth ? { Authorization: `Bearer ${auth}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) {
        setToken("");
        save("pulse-assistant-token", "");
      }
      const detail =
        typeof (result as { detail?: unknown }).detail === "string"
          ? (result as { detail: string }).detail
          : "Assistant request failed.";
      throw new Error(detail);
    }
    return result;
  }

  async function refreshChat(id: string, auth = token) {
    if (!id || !auth) return null;
    const c = (await api(`/chats/${id}`, undefined, auth)) as Chat;
    setChat(c);
    return c;
  }

  async function refreshChats(auth = token) {
    if (!auth) return;
    setChats(await api("/chats", undefined, auth));
  }

  async function connect() {
    setChecking(true);
    setError("");
    try {
      let key = token;
      if (isLocalHost()) {
        const bootstrap = (await api("/bootstrap", undefined, "")) as Bootstrap;
        key = bootstrap.token;
        setToken(key);
        save("pulse-assistant-token", key);
        setDisplayCode(bootstrap.pairing_code);
        setPairLink(buildPairUrl(bootstrap.pairing_code, bootstrap.pair_url));
      }
      if (key) {
        setStatus(await api("/status", undefined, key));
        await refreshChats(key);
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setChecking(false);
    }
  }

  /** One-shot auto-pair from ?pair=XXXXXXXX (QR / deep link). */
  useEffect(() => {
    if (autoPaired.current) return;
    const params = new URLSearchParams(location.search);
    const code = (params.get("pair") || "").replace(/\D/g, "").slice(0, 8);
    if (!code || code.length !== 8) return;
    if (token) {
      // Already paired — just clean the URL.
      autoPaired.current = true;
      stripPairFromUrl();
      return;
    }
    autoPaired.current = true;
    setAutoPairing(true);
    setError("");
    (async () => {
      try {
        const r = (await api("/pair", { code }, "")) as { token: string };
        setToken(r.token);
        save("pulse-assistant-token", r.token);
        stripPairFromUrl();
        setStatus(await api("/status", undefined, r.token));
        setChats(await api("/chats", undefined, r.token));
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
        stripPairFromUrl();
      } finally {
        setAutoPairing(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Skip bootstrap race while auto-pair is in flight; connect once we have a token or no pair param.
    const params = new URLSearchParams(location.search);
    const code = (params.get("pair") || "").replace(/\D/g, "");
    if (code.length === 8 && !token) return;
    connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!token || !chatID) return;
    let active = true;
    async function poll() {
      try {
        const c = await api(`/chats/${chatID}`);
        if (active) setChat(c);
      } catch (e) {
        if (active) setError(String(e instanceof Error ? e.message : e));
      }
    }
    poll();
    const timer = setInterval(poll, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, chatID]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [chat?.messages.map((x) => x.text).join(""), chat?.activity, chat?.approvals?.length]);

  function select(id: string) {
    setChat(null);
    setChatID(id);
    save("pulse-assistant-chat", id);
    setError("");
  }

  async function send(value = text) {
    if (!value.trim() || sending || chat?.busy) return;
    setSending(true);
    setError("");
    try {
      const c = (await api("/messages", {
        text: value,
        chat_id: chatID || null,
        mode,
        screen,
      })) as Chat;
      setChat(c);
      setChatID(c.id);
      save("pulse-assistant-chat", c.id);
      setText("");
      await refreshChats();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setSending(false);
    }
  }

  async function act(path: string, body: unknown, approvalId?: string) {
    if (acting) return;
    setActing(true);
    setError("");
    // Optimistic: clear the approval chip immediately so the UI doesn't look dead.
    if (approvalId && chat) {
      setChat({ ...chat, approvals: chat.approvals.filter((a) => a.id !== approvalId) });
    }
    try {
      await api(path, body);
      if (chatID) await refreshChat(chatID);
      await refreshChats();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      // Re-sync chat so a failed decline/approve doesn't leave stale optimistic state.
      if (chatID) {
        try {
          await refreshChat(chatID);
        } catch {
          /* keep prior error */
        }
      }
    } finally {
      setActing(false);
    }
  }

  async function pair() {
    setError("");
    try {
      const r = (await api("/pair", { code: pairCode }, "")) as { token: string };
      setToken(r.token);
      save("pulse-assistant-token", r.token);
      setStatus(await api("/status", undefined, r.token));
      setChats(await api("/chats", undefined, r.token));
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }

  const showPairBanner = Boolean(token && isLocalHost() && displayCode);
  const needsPair = !token;
  const needsConnect = Boolean(token && !status?.ready);

  return (
    <aside className={`assistant-panel ${standalone ? "standalone" : ""}`} aria-label="Pulse assistant">
      <header className="assistant-heading">
        <div className="assistant-avatar">✦</div>
        <div>
          <strong>Pulse Assistant</strong>
          <small>Powered by Codex</small>
        </div>
        <button type="button" aria-label="New conversation" title="New conversation" onClick={() => select("")}>
          ＋
        </button>
        {onClose && (
          <button type="button" aria-label="Close assistant" onClick={onClose}>
            ×
          </button>
        )}
      </header>

      <div className="assistant-context">
        <span className={status?.ready ? "connected-dot" : "offline-dot"} />
        {status?.ready ? "Connected" : "Connection needed"}
        <span>Viewing {screen}</span>
      </div>

      {showPairBanner && (
        <section className="assistant-pair-banner" aria-label="Device pairing">
          <div className="pair-code-block">
            <span className="pair-label">Pairing code</span>
            <strong className="pair-code-large">{displayCode}</strong>
            <span className="pair-hint">Valid ~10 minutes · enter only on your own phone</span>
          </div>
          {pairLink && (
            <div className="pair-qr-block">
              <LocalPairQR value={pairLink} />
              <p className="pair-url-caption">
                Scan to open <code>{pairLink}</code>
              </p>
            </div>
          )}
        </section>
      )}

      {chats.length > 0 && (
        <select
          aria-label="Conversation"
          className="conversation-select"
          value={chatID}
          onChange={(e) => select(e.target.value)}
        >
          <option value="">New conversation</option>
          {chats.map((c) => (
            <option key={c.id} value={c.id}>
              {c.busy ? "● " : ""}
              {c.title}
            </option>
          ))}
        </select>
      )}

      <div className="assistant-messages" role="log" aria-label="Conversation messages" aria-live="polite">
        {autoPairing && (
          <section className="assistant-setup">
            <h3>Pairing this device…</h3>
            <p>Saving a secure token from the QR / pair link.</p>
          </section>
        )}

        {needsPair && !autoPairing && (
          <section className="assistant-setup">
            <h3>Connect to your Mac</h3>
            <p>
              Open the assistant at localhost:8505 on your Mac and scan the QR code, or enter the 8-digit pairing code
              below. This connects this device to your source code and conversations.
            </p>
            <input
              aria-label="Pairing code"
              inputMode="numeric"
              maxLength={8}
              value={pairCode}
              onChange={(e) => setPairCode(e.target.value.replace(/\D/g, ""))}
              placeholder="8-digit pairing code"
            />
            <button type="button" disabled={pairCode.length !== 8} onClick={pair}>
              Pair device
            </button>
          </section>
        )}

        {needsConnect && !autoPairing && (
          <section className="assistant-setup">
            <h3>Your coding companion</h3>
            <p>{checking ? "Connecting to local Codex…" : status?.message || "Checking your connection…"}</p>
            <p>
              Uses the Codex account signed in on your Mac. If setup is needed, run <code>bash setup-pulse-assistant.sh</code>{" "}
              there.
            </p>
            <button type="button" onClick={connect} disabled={checking}>
              Check connection
            </button>
          </section>
        )}

        {!chat?.messages.length && status?.ready && (
          <div className="assistant-welcome">
            <h2>What would you like to work on?</h2>
            <p>I can explain your portfolio, inspect Pulse’s code, or help change the app.</p>
            {[
              "Explain my current paper P&L and missing history.",
              "Why might this screen show missing data?",
              "Suggest the next improvement to Pulse.",
            ].map((t) => (
              <button type="button" key={t} className="suggestion-chip" onClick={() => send(t)} disabled={sending || chat?.busy}>
                {t} ↗
              </button>
            ))}
          </div>
        )}

        {chat?.messages.map((m) => (
          <div className={`chat-message ${m.role}`} key={m.id}>
            <div className="message-role">{m.role === "user" ? "You" : "Pulse Assistant"}</div>
            <div className="message-text">{m.text || "…"}</div>
          </div>
        ))}

        {chat?.busy && (
          <div className="assistant-working">
            <span className="working-spinner" />
            {chat.activity || "Working…"}
          </div>
        )}

        {(error || chat?.error) && (
          <div className="notice" role="alert">
            {error || chat?.error}
          </div>
        )}

        {!!chat?.diff && (
          <details className="assistant-diff">
            <summary>Source changes</summary>
            <pre>{chat.diff}</pre>
          </details>
        )}

        {chat?.approvals.map((a) => (
          <section className="assistant-approval" key={a.id}>
            <strong>Permission requested</strong>
            <pre>{a.detail}</pre>
            {a.reason && <p>{a.reason}</p>}
            {a.cwd && <small>{a.cwd}</small>}
            <div className="approval-actions">
              <button
                type="button"
                disabled={acting}
                onClick={() => act(`/chats/${chat.id}/approvals/${a.id}`, { approve: true }, a.id)}
              >
                Approve once
              </button>
              <button
                type="button"
                disabled={acting}
                onClick={() => act(`/chats/${chat.id}/approvals/${a.id}`, { approve: false }, a.id)}
              >
                Decline
              </button>
            </div>
          </section>
        ))}

        <div ref={bottom} />
      </div>

      <footer className="assistant-composer">
        <div className="composer-controls">
          <select
            aria-label="Assistant mode"
            value={mode}
            disabled={sending || chat?.busy}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="ask">Ask · read only</option>
            <option value="edit">Edit app · repository access</option>
          </select>
          {chat?.busy && (
            <button type="button" disabled={acting} onClick={() => act(`/chats/${chat.id}/stop`, {})}>
              Stop
            </button>
          )}
        </div>
        <textarea
          aria-label="Message assistant"
          placeholder={mode === "ask" ? "Ask about the app or portfolio…" : "Describe the change to make…"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button
          type="button"
          className="assistant-send"
          disabled={!status?.ready || !text.trim() || sending || !!chat?.busy}
          onClick={() => send()}
        >
          {sending ? "Starting…" : "Send ↑"}
        </button>
        <small>
          {mode === "edit"
            ? "May edit, test, commit, rebase and push this repository. iOS changes still need a rebuild."
            : "Context: this screen, paper portfolio, news and project source. Messages are sent to OpenAI."}
        </small>
        <details
          className="pairing-details"
          onToggle={(e) => {
            if (e.currentTarget.open) connect();
          }}
        >
          <summary>Connection & device pairing</summary>
          {displayCode ? (
            <p>
              Pairing code: <strong>{displayCode}</strong>
              <br />
              Valid for 10 minutes. Enter it only on your own device.
              {pairLink && (
                <>
                  <br />
                  Or open: <code>{pairLink}</code>
                </>
              )}
            </p>
          ) : (
            <p>Pairing codes are shown in the assistant on localhost on your Mac.</p>
          )}
        </details>
      </footer>
    </aside>
  );
}
