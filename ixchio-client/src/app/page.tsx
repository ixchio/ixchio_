"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Send, Search, Loader2, AlertCircle, CheckCircle2,
  Copy, Download, RefreshCw, Clock, ChevronDown, ExternalLink,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Source = { title: string; url: string; engine: string; score: number };
type Message = {
  role: "user" | "agent";
  content: string;
  status?: string;
  progress?: number;
  currentStep?: string;
  timestamp?: string;
  sources?: Source[];
  query?: string;
};

type HistoryItem = {
  task_id: string;
  query: string;
  status: string;
  created_at: string;
  depth?: string;
};

function getTime() {
  return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text);
}

function downloadMarkdown(text: string, query: string) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${query.slice(0, 40).replace(/[^a-zA-Z0-9]/g, "_")}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---- Sources panel ----
function SourcesPanel({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;
  return (
    <div className="border-t border-white/[0.04]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-2.5 flex items-center justify-between text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
      >
        <span>{sources.length} source{sources.length !== 1 ? "s" : ""}</span>
        <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-4 space-y-1.5">
              {sources.map((s, i) => (
                <a
                  key={i}
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-xs text-neutral-400 hover:text-white transition-colors group"
                >
                  <ExternalLink size={10} className="shrink-0 opacity-40 group-hover:opacity-100" />
                  <span className="truncate">{s.title || s.url}</span>
                  <span className="shrink-0 text-neutral-600 text-[10px]">{s.engine}</span>
                </a>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}


export default function Home() {
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<"shallow" | "medium" | "deep">("medium");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // fetch history on mount
  useEffect(() => {
    fetch(`${API}/api/v1/history`).then(r => r.json()).then(d => {
      if (d.tasks) setHistory(d.tasks);
    }).catch(() => {});
  }, [messages]);

  const handleWSData = useCallback((data: Record<string, unknown>) => {
    setMessages(prev => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (!last || last.role !== "agent") return updated;

      if (data.status === "completed") {
        last.content = data.report as string;
        last.status = "completed";
        last.progress = 100;
        last.currentStep = "Done";
        last.sources = (data.sources as Source[]) || [];
        setIsSearching(false);
      } else if (data.status === "failed") {
        last.content = (data.error as string) || "Research failed";
        last.status = "error";
        setIsSearching(false);
      } else {
        last.currentStep = (data.current_step as string) || "Processing...";
        last.progress = data.progress as number;
        last.content = (data.current_step as string) || "Processing...";
      }
      return [...updated];
    });
  }, []);

  const pollTask = useCallback((taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/v1/research/${taskId}`);
        if (!res.ok) { clearInterval(interval); setIsSearching(false); return; }
        const data = await res.json();
        handleWSData(data);
        if (data.status === "completed" || data.status === "failed") clearInterval(interval);
      } catch {
        clearInterval(interval);
        setIsSearching(false);
      }
    }, 2000);
  }, [handleWSData]);

  const connectWS = useCallback((taskId: string) => {
    const wsProto = API.startsWith("https") ? "wss" : "ws";
    const wsHost = API.replace(/^https?:\/\//, "");
    const wsUrl = `${wsProto}://${wsHost}/ws/research/${taskId}`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (ev) => handleWSData(JSON.parse(ev.data));
    ws.onerror = () => { ws.close(); pollTask(taskId); };
  }, [handleWSData, pollTask]);

  const startResearch = async (q: string, d: string = depth) => {
    if (!q.trim() || isSearching) return;

    setQuery("");
    setMessages(prev => [
      ...prev,
      { role: "user", content: q, timestamp: getTime() },
      { role: "agent", content: "Starting research...", status: "starting", progress: 0, currentStep: "Queued", timestamp: getTime(), query: q },
    ]);
    setIsSearching(true);

    try {
      const res = await fetch(`${API}/api/v1/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, depth: d, max_sources: 10 }),
      });
      const data = await res.json();

      if (data.status === "completed" && data.is_demo) {
        // demo returns instantly — fetch the full task
        const taskRes = await fetch(`${API}/api/v1/research/${data.task_id}`);
        const taskData = await taskRes.json();
        handleWSData(taskData);
      } else if (data.task_id) {
        connectWS(data.task_id);
      }
    } catch {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last) {
          last.content = "Could not reach backend. Is the server running?";
          last.status = "error";
        }
        return [...updated];
      });
      setIsSearching(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    startResearch(query.trim());
  };

  const retryQuery = (q: string) => startResearch(q);

  const handleCopy = (text: string, idx: number) => {
    copyToClipboard(text);
    setCopied(idx);
    setTimeout(() => setCopied(null), 2000);
  };

  const loadFromHistory = async (item: HistoryItem) => {
    try {
      const res = await fetch(`${API}/api/v1/research/${item.task_id}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.report) {
        setMessages(prev => [
          ...prev,
          { role: "user", content: item.query, timestamp: getTime() },
          { role: "agent", content: data.report, status: "completed", progress: 100, timestamp: getTime(), sources: data.sources || [] },
        ]);
      }
      setShowHistory(false);
    } catch {}
  };

  return (
    <div className="flex flex-col h-screen bg-black text-white">
      {/* Header */}
      <header className="h-12 border-b border-white/[0.06] flex items-center justify-between px-4 md:px-6 shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold tracking-tight">ixchio</h1>
          {isSearching && (
            <span className="flex items-center gap-1.5 text-xs text-neutral-400">
              <Loader2 size={12} className="animate-spin" />
              Researching
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {history.length > 0 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="text-neutral-500 hover:text-white transition-colors p-1.5 rounded-md hover:bg-white/5 flex items-center gap-1.5 text-xs"
              title="Research history"
            >
              <Clock size={13} />
              <span className="hidden sm:inline">History</span>
            </button>
          )}
        </div>
      </header>

      {/* History dropdown */}
      <AnimatePresence>
        {showHistory && history.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-b border-white/[0.06] overflow-hidden"
          >
            <div className="px-4 md:px-6 py-3 max-h-48 overflow-y-auto space-y-1">
              {history.map((item) => (
                <button
                  key={item.task_id}
                  onClick={() => loadFromHistory(item)}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/5 transition-colors group"
                >
                  <p className="text-xs text-neutral-300 truncate group-hover:text-white">{item.query}</p>
                  <p className="text-[10px] text-neutral-600 mt-0.5 flex items-center gap-2">
                    <span className={item.status === "completed" ? "text-emerald-600" : item.status === "failed" ? "text-red-500" : "text-neutral-500"}>
                      {item.status}
                    </span>
                    {item.depth && <span>• {item.depth}</span>}
                    <span>• {new Date(item.created_at).toLocaleDateString()}</span>
                  </p>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 lg:px-16 pb-40">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="text-center space-y-4"
            >
              <h2 className="text-3xl md:text-4xl font-semibold text-white tracking-tight">
                ixchio
              </h2>
              <p className="text-neutral-500 text-sm leading-relaxed max-w-md">
                Multi-agent deep research engine. Enter a topic below and get a comprehensive, source-backed report.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 pt-2 text-xs text-neutral-600">
                <span>STORM analysis</span>
                <span className="w-1 h-1 bg-neutral-700 rounded-full" />
                <span>Adaptive search</span>
                <span className="w-1 h-1 bg-neutral-700 rounded-full" />
                <span>Reflection loops</span>
              </div>
            </motion.div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-5">
            <AnimatePresence>
              {messages.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                >
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="max-w-[80%] bg-white/[0.06] border border-white/[0.06] rounded-xl px-4 py-3">
                        <p className="text-sm text-neutral-200 leading-relaxed">{msg.content}</p>
                        <span className="text-[10px] text-neutral-600 mt-1 block">{msg.timestamp}</span>
                      </div>
                    </div>
                  ) : msg.status !== "completed" && msg.status !== "error" ? (
                    <div className="border border-white/[0.06] rounded-xl px-5 py-4">
                      <div className="flex items-center gap-3">
                        <Loader2 size={16} className="animate-spin text-neutral-400" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-neutral-300 truncate">{msg.currentStep || msg.content}</p>
                          <div className="mt-2.5 h-[2px] bg-white/[0.04] rounded-full overflow-hidden">
                            <motion.div
                              className="h-full bg-white/30 rounded-full"
                              initial={{ width: 0 }}
                              animate={{ width: `${msg.progress || 0}%` }}
                              transition={{ duration: 0.5 }}
                            />
                          </div>
                        </div>
                        <span className="text-xs text-neutral-500 tabular-nums shrink-0">
                          {msg.progress || 0}%
                        </span>
                      </div>
                    </div>
                  ) : msg.status === "error" ? (
                    <div className="border border-red-500/20 rounded-xl px-5 py-4">
                      <div className="flex items-start gap-2">
                        <AlertCircle size={14} className="mt-0.5 text-red-400 shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm text-red-300">{msg.content}</p>
                          {msg.query && (
                            <button
                              onClick={() => retryQuery(msg.query!)}
                              className="mt-2 flex items-center gap-1.5 text-xs text-neutral-400 hover:text-white transition-colors"
                            >
                              <RefreshCw size={11} /> Retry
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="border border-white/[0.06] rounded-xl overflow-hidden">
                      <div className="px-5 py-3 border-b border-white/[0.04] flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={13} className="text-emerald-600" />
                          <span className="text-xs text-neutral-500">Research complete</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleCopy(msg.content, i)}
                            className="p-1.5 rounded-md text-neutral-500 hover:text-white hover:bg-white/5 transition-colors"
                            title="Copy markdown"
                          >
                            {copied === i ? <CheckCircle2 size={12} className="text-emerald-500" /> : <Copy size={12} />}
                          </button>
                          <button
                            onClick={() => downloadMarkdown(msg.content, messages[i - 1]?.content || "research")}
                            className="p-1.5 rounded-md text-neutral-500 hover:text-white hover:bg-white/5 transition-colors"
                            title="Download .md"
                          >
                            <Download size={12} />
                          </button>
                          <span className="text-[10px] text-neutral-600 ml-1">{msg.timestamp}</span>
                        </div>
                      </div>
                      <div className="px-5 py-6 md:px-8 research-prose text-sm">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                      <SourcesPanel sources={msg.sources || []} />
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={endRef} className="h-4" />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="absolute bottom-0 left-0 right-0 p-4 md:p-6 z-10">
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/95 to-transparent pointer-events-none" />
        <div className="max-w-3xl mx-auto relative">
          <form onSubmit={submit}>
            <div className="border border-white/10 rounded-xl bg-black/80 backdrop-blur-sm flex items-center transition-colors focus-within:border-white/20">
              <div className="pl-4 text-neutral-500">
                <Search size={16} />
              </div>
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="What would you like to research?"
                disabled={isSearching}
                maxLength={500}
                spellCheck={false}
                className="flex-1 bg-transparent text-white text-sm pl-3 pr-1 py-3.5 md:py-4 outline-none placeholder:text-neutral-600 disabled:opacity-40"
              />
              {/* Depth selector */}
              <select
                value={depth}
                onChange={e => setDepth(e.target.value as "shallow" | "medium" | "deep")}
                disabled={isSearching}
                className="bg-transparent text-neutral-500 text-[11px] border-none outline-none cursor-pointer hover:text-white transition-colors disabled:opacity-40 mr-1 appearance-none text-center"
                title="Research depth"
              >
                <option value="shallow" className="bg-black">⚡ Quick</option>
                <option value="medium" className="bg-black">⚖️ Standard</option>
                <option value="deep" className="bg-black">🔬 Deep</option>
              </select>
              <button
                type="submit"
                disabled={!query.trim() || isSearching}
                className="mr-2 p-2 rounded-lg bg-white text-black disabled:opacity-20 hover:opacity-90 transition-opacity"
              >
                <Send size={14} />
              </button>
            </div>
          </form>

          <div className="flex items-center justify-center gap-3 mt-2.5 text-[10px] text-neutral-600">
            <span>v4.0</span>
            <span className="w-0.5 h-0.5 bg-neutral-700 rounded-full" />
            <button
              type="button"
              onClick={() => startResearch("demo")}
              disabled={isSearching}
              className="text-neutral-400 hover:text-white transition-colors disabled:opacity-40"
              title="Load demo research"
            >
              Try demo
            </button>
            {query.length > 0 && (
              <>
                <span className="w-0.5 h-0.5 bg-neutral-700 rounded-full" />
                <span className={query.length > 450 ? "text-red-400" : ""}>{query.length}/500</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
