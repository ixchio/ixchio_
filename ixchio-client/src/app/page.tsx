"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/* ── types ── */
type Source = { title: string; url: string; engine: string; score: number };
type Message = {
  role: "user" | "agent";
  content: string;
  status?: string;
  progress?: number;
  currentStep?: string;
  sources?: Source[];
  query?: string;
};
type HistoryItem = { task_id: string; query: string; status: string; created_at: string };

/* ── helpers ── */
function copyText(t: string) { navigator.clipboard.writeText(t); }
function dlMd(t: string, q: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([t], { type: "text/markdown" }));
  a.download = `${q.slice(0, 40).replace(/[^a-z0-9]/gi, "_")}.md`;
  a.click();
}
function extractDomain(url: string) {
  try { return new URL(url).hostname.replace("www.", ""); } catch { return url; }
}
function timeAgo(d: string) {
  const s = Math.floor((Date.now() - new Date(d).getTime()) / 1e3);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const DEPTH_LABELS = { shallow: "Quick", medium: "Standard", deep: "Deep" } as const;

/* ── hooks ── */
function useTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const prefersDark = saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(prefersDark);
    document.documentElement.classList.toggle("dark", prefersDark);
  }, []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };
  return { dark, toggle };
}

/* ── small components ── */
function ThemeToggle({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button onClick={toggle} title={dark ? "Light mode" : "Dark mode"}
      className="w-7 h-7 rounded-full flex items-center justify-center transition-colors"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <span className="text-[11px]">{dark ? "☀" : "☽"}</span>
    </button>
  );
}

function SourceChip({ src }: { src: Source }) {
  return (
    <a href={src.url} target="_blank" rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] transition-colors"
      style={{ background: "var(--src-bg)", color: "var(--muted2)", border: "1px solid var(--border)" }}>
      <span className="truncate max-w-[160px]">{src.title || extractDomain(src.url)}</span>
      <span style={{ color: "var(--muted)" }}>↗</span>
    </a>
  );
}

function SourcesBar({ sources }: { sources: Source[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!sources?.length) return null;
  const visible = expanded ? sources : sources.slice(0, 4);
  return (
    <div className="fade-in stagger-2 mt-6 pt-5" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: "var(--muted)" }}>
          {sources.length} source{sources.length !== 1 && "s"}
        </span>
        {sources.length > 4 && (
          <button onClick={() => setExpanded(!expanded)}
            className="text-[11px] transition-colors" style={{ color: "var(--muted)" }}>
            {expanded ? "Show less" : `+${sources.length - 4} more`}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((s, i) => <SourceChip key={i} src={s} />)}
      </div>
    </div>
  );
}

function ProgressIndicator({ step, progress }: { step: string; progress: number }) {
  return (
    <div className="py-6 fade-in">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-2 h-2 rounded-full" style={{ background: "var(--bar)", animation: "pulse-bar 1.5s infinite" }} />
        <p className="text-sm" style={{ color: "var(--muted2)" }}>{step || "Initializing..."}</p>
      </div>
      <div className="h-[2px] rounded-full overflow-hidden" style={{ background: "var(--bar-track)" }}>
        <div className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ background: "var(--bar)", width: `${Math.max(progress || 0, 2)}%` }} />
      </div>
      <p className="text-[11px] mt-2 tabular-nums font-medium" style={{ color: "var(--muted)" }}>{progress || 0}%</p>
    </div>
  );
}

function ActionBar({ content, query, copied, onCopy, idx }: {
  content: string; query: string; copied: number; onCopy: (t: string, i: number) => void; idx: number;
}) {
  return (
    <div className="flex items-center gap-1 mb-5 fade-in">
      {[
        { label: copied === idx ? "Copied" : "Copy", action: () => onCopy(content, idx) },
        { label: "Download", action: () => dlMd(content, query) },
      ].map((btn) => (
        <button key={btn.label} onClick={btn.action}
          className="px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors"
          style={{ color: "var(--muted2)", background: "var(--surface)", border: "1px solid var(--border)" }}>
          {btn.label}
        </button>
      ))}
    </div>
  );
}

/* ── search input ── */
function SearchBar({ value, onChange, depth, onDepth, onSubmit, disabled, placeholder, autoFocus, variant }: {
  value: string; onChange: (v: string) => void; depth: string; onDepth: (d: string) => void;
  onSubmit: () => void; disabled?: boolean; placeholder: string; autoFocus?: boolean;
  variant: "home" | "conv";
}) {
  const isHome = variant === "home";
  return (
    <form onSubmit={e => { e.preventDefault(); onSubmit(); }} className="w-full">
      <div className="flex items-center gap-2 rounded-xl px-4 transition-all"
        style={{
          border: "1px solid var(--border)",
          background: "var(--bg)",
          boxShadow: `0 0 0 0px var(--ring)`,
          height: isHome ? "52px" : "48px",
        }}
        onFocus={e => { (e.currentTarget as HTMLElement).style.boxShadow = `0 0 0 3px var(--ring)`; }}
        onBlur={e => { (e.currentTarget as HTMLElement).style.boxShadow = `0 0 0 0px var(--ring)`; }}>
        <input
          type="text" value={value} onChange={e => onChange(e.target.value)}
          placeholder={placeholder} disabled={disabled} maxLength={500}
          spellCheck={false} autoFocus={autoFocus} autoComplete="off"
          className="flex-1 bg-transparent outline-none disabled:opacity-30"
          style={{ color: "var(--fg)", caretColor: "var(--fg)", fontSize: isHome ? "15px" : "14px" }}
        />
        <select value={depth} onChange={e => onDepth(e.target.value)} disabled={disabled}
          className="bg-transparent outline-none cursor-pointer text-[12px] disabled:opacity-30 font-medium"
          style={{ color: "var(--muted)" }}>
          <option value="shallow">Quick</option>
          <option value="medium">Standard</option>
          <option value="deep">Deep</option>
        </select>
        <button type="submit" disabled={!value.trim() || disabled}
          className="flex items-center justify-center rounded-lg font-medium disabled:opacity-15 transition-all"
          style={{
            background: "var(--accent)", color: "var(--accent-fg)",
            fontSize: "12px", padding: "6px 16px", letterSpacing: ".01em",
          }}>
          →
        </button>
      </div>
    </form>
  );
}

/* ── main ── */
export default function Home() {
  const { dark, toggle } = useTheme();
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<"shallow" | "medium" | "deep">("medium");
  const [messages, setMessages] = useState<Message[]>([]);
  const [searching, setSearching] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHist, setShowHist] = useState(false);
  const [copied, setCopied] = useState(-1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const fetchHistory = useCallback(() => {
    fetch(`${API}/api/v1/history`).then(r => r.json()).then(d => d.tasks && setHistory(d.tasks)).catch(() => {});
  }, []);
  useEffect(fetchHistory, [fetchHistory]);

  const onData = useCallback((d: Record<string, unknown>) => {
    setMessages(prev => {
      const msgs = [...prev];
      const last = msgs[msgs.length - 1];
      if (!last || last.role !== "agent") return msgs;
      if (d.status === "completed") {
        last.content = d.report as string;
        last.status = "completed";
        last.progress = 100;
        last.sources = (d.sources as Source[]) || [];
        setSearching(false);
        fetchHistory();
      } else if (d.status === "failed") {
        last.content = (d.error as string) || "Research failed.";
        last.status = "error";
        setSearching(false);
      } else {
        last.currentStep = (d.current_step as string) || "";
        last.progress = d.progress as number;
      }
      return [...msgs];
    });
  }, [fetchHistory]);

  const poll = useCallback((id: string) => {
    const iv = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/v1/research/${id}`);
        if (!r.ok) { clearInterval(iv); setSearching(false); return; }
        const d = await r.json();
        onData(d);
        if (d.status === "completed" || d.status === "failed") clearInterval(iv);
      } catch { clearInterval(iv); setSearching(false); }
    }, 2000);
  }, [onData]);

  const ws = useCallback((id: string) => {
    const p = API.startsWith("https") ? "wss" : "ws";
    const h = API.replace(/^https?:\/\//, "");
    let completed = false;
    const sock = new WebSocket(`${p}://${h}/ws/research/${id}`);
    sock.onmessage = (e) => {
      const d = JSON.parse(e.data);
      onData(d);
      if (d.status === "completed" || d.status === "failed") completed = true;
    };
    sock.onerror = () => { sock.close(); if (!completed) poll(id); };
    sock.onclose = () => { if (!completed) poll(id); };
  }, [onData, poll]);

  const go = async (q: string) => {
    if (!q.trim() || searching) return;
    const text = q.trim();
    setQuery("");
    setMessages(p => [...p,
      { role: "user", content: text },
      { role: "agent", content: "", status: "loading", progress: 0, currentStep: "Starting research...", query: text },
    ]);
    setSearching(true);
    try {
      const r = await fetch(`${API}/api/v1/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text, depth, max_sources: 10 }),
      });
      if (!r.ok) throw new Error(`Server error (${r.status})`);
      const d = await r.json();
      if (d.status === "completed" && d.is_demo) {
        const tr = await fetch(`${API}/api/v1/research/${d.task_id}`);
        onData(await tr.json());
      } else if (d.task_id) ws(d.task_id);
    } catch {
      setMessages(p => {
        const m = [...p]; const l = m[m.length - 1];
        if (l) { l.content = "Could not reach the server."; l.status = "error"; }
        return m;
      });
      setSearching(false);
    }
  };

  const loadHist = async (item: HistoryItem) => {
    const r = await fetch(`${API}/api/v1/research/${item.task_id}`).catch(() => null);
    if (!r?.ok) return;
    const d = await r.json();
    if (d.report) {
      setMessages(p => [...p,
        { role: "user", content: item.query },
        { role: "agent", content: d.report, status: "completed", progress: 100, sources: d.sources || [] },
      ]);
    }
    setShowHist(false);
  };

  const newSearch = () => { setMessages([]); setSearching(false); setShowHist(false); };
  const doCopy = (t: string, i: number) => { copyText(t); setCopied(i); setTimeout(() => setCopied(-1), 1500); };

  /* ── HOME SCREEN ── */
  if (messages.length === 0) return (
    <div className="h-screen flex flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <div />
        <div className="flex items-center gap-2">
          {history.length > 0 && (
            <button onClick={() => setShowHist(!showHist)}
              className="px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors"
              style={{ color: "var(--muted2)", background: "var(--surface)", border: "1px solid var(--border)" }}>
              History
            </button>
          )}
          <ThemeToggle dark={dark} toggle={toggle} />
        </div>
      </header>

      {showHist && history.length > 0 && (
        <div className="mx-auto w-full max-w-xl px-4 mb-4 fade-in">
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
            {history.map((h, i) => (
              <button key={h.task_id} onClick={() => loadHist(h)}
                className="w-full px-4 py-3 text-left flex items-center justify-between transition-colors"
                style={{ borderBottom: i < history.length - 1 ? "1px solid var(--border2)" : "none", background: "var(--bg)" }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--hover)"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "var(--bg)"; }}>
                <span className="text-[13px] truncate flex-1 mr-3" style={{ color: "var(--fg)" }}>{h.query}</span>
                <span className="text-[10px] shrink-0" style={{ color: "var(--muted)" }}>{timeAgo(h.created_at)}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col items-center justify-center px-4 -mt-16">
        <div className="w-full max-w-xl text-center">
          <h1 className="text-[2.75rem] md:text-[3.25rem] font-semibold tracking-[-0.04em] mb-2"
            style={{ color: "var(--fg)" }}>ixchio</h1>
          <p className="text-[15px] mb-10" style={{ color: "var(--muted)", lineHeight: 1.5 }}>
            Deep research on any topic. Source-backed reports in minutes.
          </p>
          <SearchBar value={query} onChange={setQuery} depth={depth} onDepth={d => setDepth(d as typeof depth)}
            onSubmit={() => go(query)} placeholder="What do you want to research?"
            autoFocus variant="home" />
          <div className="mt-5 flex items-center justify-center gap-2 flex-wrap">
            {["How does mRNA vaccine technology work", "Latest advances in nuclear fusion", "Impact of AI on job markets 2025"].map(q => (
              <button key={q} onClick={() => go(q)}
                className="px-3 py-1.5 rounded-lg text-[11px] transition-colors"
                style={{ color: "var(--muted)", background: "var(--surface)", border: "1px solid var(--border2)" }}>
                {q.length > 35 ? q.slice(0, 35) + "…" : q}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  /* ── CONVERSATION VIEW ── */
  return (
    <div className="flex flex-col h-screen">
      <header className="h-12 flex items-center justify-between px-5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
        <button onClick={newSearch} className="text-sm font-semibold tracking-tight transition-opacity hover:opacity-70"
          style={{ color: "var(--fg)" }}>ixchio</button>
        <div className="flex items-center gap-2">
          {searching && (
            <span className="text-[11px] font-medium px-2.5 py-1 rounded-md"
              style={{ color: "var(--muted2)", background: "var(--surface)", animation: "pulse-bar 2s infinite" }}>
              Researching
            </span>
          )}
          {history.length > 0 && (
            <button onClick={() => setShowHist(!showHist)}
              className="px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors"
              style={{ color: "var(--muted2)", background: showHist ? "var(--hover)" : "transparent" }}>
              History
            </button>
          )}
          <button onClick={newSearch}
            className="px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors"
            style={{ color: "var(--muted2)" }}>
            New
          </button>
          <ThemeToggle dark={dark} toggle={toggle} />
        </div>
      </header>

      {showHist && (
        <div className="px-5 py-2 max-h-44 overflow-y-auto fade-in"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--bg2)" }}>
          {history.map(h => (
            <button key={h.task_id} onClick={() => loadHist(h)}
              className="flex items-center justify-between w-full text-left py-2 transition-colors rounded px-2"
              style={{ color: "var(--muted2)" }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--hover)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
              <span className="text-[12px] truncate flex-1 mr-3" style={{ color: "var(--fg)" }}>{h.query}</span>
              <span className="text-[10px] shrink-0">{timeAgo(h.created_at)}</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 md:px-0 pb-32">
        <div className="max-w-2xl mx-auto py-8 space-y-2">
          {messages.map((msg, i) => (
            <div key={i} className="fade-in">
              {msg.role === "user" ? (
                <div className="pt-4 pb-2">
                  <p className="text-base font-semibold tracking-tight" style={{ color: "var(--fg)" }}>{msg.content}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] uppercase tracking-wider font-medium"
                      style={{ color: "var(--muted)" }}>{DEPTH_LABELS[depth]} research</span>
                  </div>
                </div>
              ) : msg.status === "loading" || (msg.status !== "completed" && msg.status !== "error") ? (
                <ProgressIndicator step={msg.currentStep || ""} progress={msg.progress || 0} />
              ) : msg.status === "error" ? (
                <div className="py-4 fade-in">
                  <div className="rounded-xl px-5 py-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                    <p className="text-sm" style={{ color: "var(--muted2)" }}>{msg.content}</p>
                    {msg.query && (
                      <button onClick={() => go(msg.query!)}
                        className="mt-3 text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors"
                        style={{ color: "var(--accent-fg)", background: "var(--accent)" }}>
                        Retry
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="fade-in stagger-1">
                  <ActionBar content={msg.content} query={messages[i - 1]?.content || "research"}
                    copied={copied} onCopy={doCopy} idx={i} />
                  <div className="prose">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                  <SourcesBar sources={msg.sources || []} />
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 px-4 pb-4 pt-6"
        style={{ background: "linear-gradient(to top, var(--bg) 60%, transparent)" }}>
        <div className="max-w-2xl mx-auto">
          <SearchBar value={query} onChange={setQuery} depth={depth} onDepth={d => setDepth(d as typeof depth)}
            onSubmit={() => go(query)} disabled={searching}
            placeholder="Ask a follow-up or research something new..." variant="conv" />
        </div>
      </div>
    </div>
  );
}
