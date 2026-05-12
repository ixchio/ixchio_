"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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

function copyText(t: string) { navigator.clipboard.writeText(t); }
function dlMd(t: string, q: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([t], { type: "text/markdown" }));
  a.download = `${q.slice(0, 40).replace(/[^a-z0-9]/gi, "_")}.md`;
  a.click();
}

function Sources({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;
  return (
    <div className="border-t border-neutral-100 mt-6 pt-3">
      <button onClick={() => setOpen(!open)} className="text-xs text-neutral-400 hover:text-black">
        {sources.length} source{sources.length !== 1 && "s"} {open ? "−" : "+"}
      </button>
      {open && (
        <div className="mt-2 space-y-1">
          {sources.map((s, i) => (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
              className="block text-xs text-neutral-500 hover:text-black truncate">
              {s.title || s.url}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<"shallow" | "medium" | "deep">("medium");
  const [messages, setMessages] = useState<Message[]>([]);
  const [searching, setSearching] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHist, setShowHist] = useState(false);
  const [copied, setCopied] = useState(-1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => {
    fetch(`${API}/api/v1/history`).then(r => r.json()).then(d => d.tasks && setHistory(d.tasks)).catch(() => {});
  }, [messages]);

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
  }, []);

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
    const s = new WebSocket(`${p}://${h}/ws/research/${id}`);
    s.onmessage = (e) => onData(JSON.parse(e.data));
    s.onerror = () => { s.close(); poll(id); };
  }, [onData, poll]);

  const go = async (q: string) => {
    if (!q.trim() || searching) return;
    setQuery("");
    setMessages(p => [...p,
      { role: "user", content: q },
      { role: "agent", content: "", status: "loading", progress: 0, currentStep: "Queued", query: q },
    ]);
    setSearching(true);
    try {
      const r = await fetch(`${API}/api/v1/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, depth, max_sources: 10 }),
      });
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

  const doCopy = (t: string, i: number) => { copyText(t); setCopied(i); setTimeout(() => setCopied(-1), 1500); };

  // empty state
  if (messages.length === 0) return (
    <div className="h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-xl text-center">
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-black mb-3">ixchio</h1>
        <p className="text-neutral-400 text-sm mb-12">Research any topic. Get a comprehensive report.</p>

        <form onSubmit={e => { e.preventDefault(); go(query.trim()); }} className="w-full">
          <div className="flex items-center border border-neutral-200 rounded-lg px-4 py-3 focus-within:border-black transition-colors">
            <input
              type="text" value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Enter a research topic..."
              maxLength={500} spellCheck={false} autoFocus
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-neutral-300"
            />
            <select value={depth} onChange={e => setDepth(e.target.value as typeof depth)}
              className="text-xs text-neutral-400 bg-transparent outline-none cursor-pointer mr-3">
              <option value="shallow">Quick</option>
              <option value="medium">Standard</option>
              <option value="deep">Deep</option>
            </select>
            <button type="submit" disabled={!query.trim()}
              className="text-xs font-medium text-white bg-black px-4 py-1.5 rounded-md disabled:opacity-20 hover:opacity-80 transition-opacity">
              Research
            </button>
          </div>
        </form>

        <div className="mt-6 flex items-center justify-center gap-4 text-xs text-neutral-300">
          <button onClick={() => go("demo")} className="hover:text-black transition-colors">Try demo</button>
          {history.length > 0 && <>
            <span className="text-neutral-200">·</span>
            <button onClick={() => setShowHist(!showHist)} className="hover:text-black transition-colors">
              History ({history.length})
            </button>
          </>}
        </div>

        {showHist && history.length > 0 && (
          <div className="mt-4 border border-neutral-100 rounded-lg max-h-48 overflow-y-auto text-left">
            {history.map(h => (
              <button key={h.task_id} onClick={() => loadHist(h)}
                className="w-full px-4 py-2.5 text-left hover:bg-neutral-50 border-b border-neutral-50 last:border-0">
                <p className="text-xs text-black truncate">{h.query}</p>
                <p className="text-[10px] text-neutral-400 mt-0.5">{h.status} · {new Date(h.created_at).toLocaleDateString()}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  // conversation view
  return (
    <div className="flex flex-col h-screen">
      <header className="h-11 border-b border-neutral-100 flex items-center justify-between px-5 shrink-0">
        <span className="text-sm font-semibold tracking-tight">ixchio</span>
        <div className="flex items-center gap-3 text-xs text-neutral-400">
          {searching && <span className="animate-pulse">Researching...</span>}
          {history.length > 0 && (
            <button onClick={() => setShowHist(!showHist)} className="hover:text-black transition-colors">History</button>
          )}
        </div>
      </header>

      {showHist && (
        <div className="border-b border-neutral-100 px-5 py-2 max-h-40 overflow-y-auto">
          {history.map(h => (
            <button key={h.task_id} onClick={() => loadHist(h)}
              className="block w-full text-left py-1.5 hover:text-black text-xs text-neutral-500 truncate">
              {h.query}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 md:px-0 pb-32">
        <div className="max-w-2xl mx-auto py-8 space-y-6">
          {messages.map((msg, i) => (
            <div key={i}>
              {msg.role === "user" ? (
                <p className="text-sm font-medium text-black mb-1">{msg.content}</p>
              ) : msg.status === "loading" || (msg.status !== "completed" && msg.status !== "error") ? (
                <div className="py-4">
                  <p className="text-sm text-neutral-400">{msg.currentStep || "Processing..."}</p>
                  <div className="mt-2 h-px bg-neutral-100 overflow-hidden">
                    <div className="h-full bg-black transition-all duration-500" style={{ width: `${msg.progress || 0}%` }} />
                  </div>
                  <p className="text-[11px] text-neutral-300 mt-1 tabular-nums">{msg.progress || 0}%</p>
                </div>
              ) : msg.status === "error" ? (
                <div className="py-3">
                  <p className="text-sm text-neutral-500">{msg.content}</p>
                  {msg.query && (
                    <button onClick={() => go(msg.query!)}
                      className="mt-1.5 text-xs text-neutral-400 hover:text-black transition-colors underline">
                      Retry
                    </button>
                  )}
                </div>
              ) : (
                <div>
                  <div className="flex items-center gap-3 mb-4 text-xs text-neutral-400">
                    <span>Report</span>
                    <button onClick={() => doCopy(msg.content, i)} className="hover:text-black transition-colors">
                      {copied === i ? "Copied" : "Copy"}
                    </button>
                    <button onClick={() => dlMd(msg.content, messages[i - 1]?.content || "research")}
                      className="hover:text-black transition-colors">Download</button>
                  </div>
                  <div className="prose text-sm">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                  <Sources sources={msg.sources || []} />
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white to-white/0 pt-8 pb-4 px-4">
        <form onSubmit={e => { e.preventDefault(); go(query.trim()); }} className="max-w-2xl mx-auto">
          <div className="flex items-center border border-neutral-200 rounded-lg px-4 py-3 bg-white focus-within:border-black transition-colors">
            <input
              type="text" value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Ask a follow-up or new topic..."
              disabled={searching} maxLength={500} spellCheck={false}
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-neutral-300 disabled:opacity-30"
            />
            <select value={depth} onChange={e => setDepth(e.target.value as typeof depth)}
              disabled={searching}
              className="text-xs text-neutral-400 bg-transparent outline-none cursor-pointer mr-3 disabled:opacity-30">
              <option value="shallow">Quick</option>
              <option value="medium">Standard</option>
              <option value="deep">Deep</option>
            </select>
            <button type="submit" disabled={!query.trim() || searching}
              className="text-xs font-medium text-white bg-black px-4 py-1.5 rounded-md disabled:opacity-20 hover:opacity-80 transition-opacity">
              Research
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
