"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Send, Search, ArrowRight, LogOut, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Message = {
  role: "user" | "agent";
  content: string;
  status?: string;
  progress?: number;
  timestamp?: string;
};

// ---- helpers ----
function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ixchio_token");
}
function setToken(t: string) { localStorage.setItem("ixchio_token", t); }
function clearToken() { localStorage.removeItem("ixchio_token"); }

function getTime() {
  return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}


// ---- auth screen ----
function AuthScreen({ onAuth }: { onAuth: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError("");
    if (!email.trim() || !password.trim()) {
      setError("Email and password are required");
      return;
    }
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/auth/login" : "/auth/signup";
      const body: Record<string, string> = { email: email.trim(), password };
      if (mode === "signup") body.name = name.trim();

      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");
      setToken(data.access_token);
      onAuth();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        {/* Title */}
        <div className="text-center mb-10">
          <h1 className="text-2xl font-semibold text-white tracking-tight mb-1">ixchio</h1>
          <p className="text-sm text-neutral-500">Deep research, simplified.</p>
        </div>

        {/* Mode toggle */}
        <div className="flex mb-6 border-b border-white/10">
          {(["login", "signup"] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(""); }}
              className={`flex-1 pb-3 text-sm font-medium transition-colors ${
                mode === m
                  ? "text-white border-b-2 border-white"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {m === "login" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        {/* Form */}
        <div className="space-y-3">
          <AnimatePresence>
            {mode === "signup" && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <input
                  type="text"
                  placeholder="Name"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className="w-full bg-transparent border border-white/10 text-white text-sm px-4 py-3 rounded-lg outline-none transition-colors focus:border-white/30 placeholder:text-neutral-600"
                />
              </motion.div>
            )}
          </AnimatePresence>

          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full bg-transparent border border-white/10 text-white text-sm px-4 py-3 rounded-lg outline-none transition-colors focus:border-white/30 placeholder:text-neutral-600"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && submit()}
            className="w-full bg-transparent border border-white/10 text-white text-sm px-4 py-3 rounded-lg outline-none transition-colors focus:border-white/30 placeholder:text-neutral-600"
          />
        </div>

        {error && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-3 text-sm text-neutral-400 flex items-start gap-2"
          >
            <AlertCircle size={14} className="mt-0.5 shrink-0 text-white" />
            {error}
          </motion.p>
        )}

        <button
          onClick={submit}
          disabled={loading}
          className="w-full mt-6 bg-white text-black text-sm font-medium py-3 rounded-lg transition-opacity hover:opacity-90 disabled:opacity-40 flex items-center justify-center gap-2"
        >
          {loading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <>
              {mode === "login" ? "Sign in" : "Create account"}
              <ArrowRight size={14} />
            </>
          )}
        </button>

        <p className="text-center text-neutral-600 text-xs mt-6">
          {mode === "login" ? "No account? " : "Already have an account? "}
          <button
            onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}
            className="text-white hover:underline"
          >
            {mode === "login" ? "Create one" : "Sign in"}
          </button>
        </p>
      </motion.div>
    </div>
  );
}


// ---- main ----
export default function Home() {
  const [authed, setAuthed] = useState(false);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setAuthed(!!getToken()); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleWSData = useCallback((data: Record<string, unknown>) => {
    setMessages(prev => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (!last || last.role !== "agent") return updated;

      if (data.status === "completed") {
        last.content = data.report as string;
        last.status = "completed";
        last.progress = 100;
        setIsSearching(false);
      } else if (data.status === "failed") {
        last.content = (data.error as string) || "Research failed";
        last.status = "error";
        setIsSearching(false);
      } else {
        last.status = data.current_step as string;
        last.progress = data.progress as number;
        last.content = (data.current_step as string) || "Processing...";
      }
      return updated;
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
    const token = getToken();
    const wsUrl = `${wsProto}://${wsHost}/ws/research/${taskId}${token ? `?token=${token}` : ""}`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (ev) => handleWSData(JSON.parse(ev.data));
    ws.onerror = () => { ws.close(); pollTask(taskId); };
  }, [handleWSData, pollTask]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isSearching) return;

    const q = query.trim();
    setQuery("");
    setMessages(prev => [
      ...prev,
      { role: "user", content: q, timestamp: getTime() },
      { role: "agent", content: "Starting research...", status: "starting", progress: 0, timestamp: getTime() },
    ]);
    setIsSearching(true);

    try {
      const token = getToken();
      const res = await fetch(`${API}/api/v1/research`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query: q, depth: "medium", max_sources: 10, mode: "standard" }),
      });

      if (res.status === 401) {
        clearToken();
        setAuthed(false);
        setIsSearching(false);
        return;
      }

      const data = await res.json();
      if (data.task_id) connectWS(data.task_id);
    } catch {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last) {
          last.content = "Could not reach backend. Is the server running?";
          last.status = "error";
        }
        return updated;
      });
      setIsSearching(false);
    }
  };

  if (!authed) return <AuthScreen onAuth={() => setAuthed(true)} />;

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
        <button
          onClick={() => { clearToken(); setAuthed(false); }}
          className="text-neutral-500 hover:text-white transition-colors p-1.5 rounded-md hover:bg-white/5"
          title="Sign out"
        >
          <LogOut size={14} />
        </button>
      </header>

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
              <div className="flex items-center justify-center gap-4 pt-2 text-xs text-neutral-600">
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
                          <p className="text-sm text-neutral-300 truncate">{msg.content}</p>
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
                    <div className="border border-white/[0.06] rounded-xl px-5 py-4">
                      <div className="flex items-start gap-2">
                        <AlertCircle size={14} className="mt-0.5 text-neutral-400 shrink-0" />
                        <p className="text-sm text-neutral-400">{msg.content}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="border border-white/[0.06] rounded-xl overflow-hidden">
                      <div className="px-5 py-3 border-b border-white/[0.04] flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={13} className="text-neutral-500" />
                          <span className="text-xs text-neutral-500">Research complete</span>
                        </div>
                        <span className="text-[10px] text-neutral-600">{msg.timestamp}</span>
                      </div>
                      <div className="px-5 py-6 md:px-8 research-prose text-sm">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
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
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="What would you like to research?"
                disabled={isSearching}
                spellCheck={false}
                className="flex-1 bg-transparent text-white text-sm pl-3 pr-3 py-3.5 md:py-4 outline-none placeholder:text-neutral-600 disabled:opacity-40"
              />
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
            <span>v3.0</span>
            <span className="w-0.5 h-0.5 bg-neutral-700 rounded-full" />
            <button
              type="button"
              onClick={() => setQuery("demo")}
              className="text-neutral-400 hover:text-white transition-colors"
              title="Load demo research"
            >
              Try demo
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
