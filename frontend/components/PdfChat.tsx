"use client";

import { FormEvent, useMemo, useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Bot, User, FileText, Moon, Sun } from "lucide-react";

type Source = {
  content: string;
  score: number;
  page_number?: number | null;
};

type ChatTurn = {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

// Helper to detect if text is predominantly Arabic (RTL)
function getDirection(text: string): "rtl" | "ltr" {
  const arabicPattern = /[\u0600-\u06FF]/;
  return arabicPattern.test(text) ? "rtl" : "ltr";
}

export default function PdfChat() {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [mounted, setMounted] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const canAsk = useMemo(() => prompt.trim().length > 0 && !busy, [prompt, busy]);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    setMounted(true);
    const savedTheme = localStorage.getItem("theme") as "dark" | "light" | null;
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute("data-theme", savedTheme);
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [chat]);

  const toggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
  };

  const handleAsk = async (e: FormEvent) => {
    e.preventDefault();
    if (!canAsk) return;

    const userText = prompt.trim();
    setPrompt("");
    const assistantIndex = chat.length + 1;
    setChat((prev) => [...prev, { role: "user", text: userText }, { role: "assistant", text: "" }]);
    setBusy(true);

    try {
      const res = await fetch(`${API_BASE}/chat/stream/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText })
      });
      if (!res.ok || !res.body) {
        throw new Error("Chat stream request failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line) as { type: string; text?: string; sources?: Source[]; error?: string };

            if (event.type === "delta" && event.text) {
              setChat((prev) =>
                prev.map((turn, idx) => (idx === assistantIndex ? { ...turn, text: turn.text + event.text } : turn))
              );
            }

            if (event.type === "sources" && event.sources) {
              setChat((prev) =>
                prev.map((turn, idx) => (idx === assistantIndex ? { ...turn, sources: event.sources } : turn))
              );
            }

            if (event.type === "error") {
              throw new Error(event.error || "Streaming error");
            }
          } catch (e) {
            console.error("Error parsing stream line:", line, e);
          }
        }
      }
    } catch (err) {
      setChat((prev) =>
        prev.map((turn, idx) =>
          idx === assistantIndex ? { ...turn, text: err instanceof Error ? err.message : "Something went wrong" } : turn
        )
      );
    } finally {
      setBusy(false);
    }
  };

  if (!mounted) return null;

  return (
    <main className="shell">
      <header className="panel" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <FileText size={32} color="var(--primary)" />
          <div>
            <h1>Policy Navigator</h1>
            <p className="status">Connected to: Book and policies.pdf</p>
          </div>
        </div>
        <button onClick={toggleTheme} className="theme-toggle" title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
          {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
        </button>
      </header>

      <section className="chatlog">
        {chat.length === 0 && (
          <div style={{ textAlign: "center", padding: "4rem 2rem", opacity: 0.5 }}>
            <Bot size={48} style={{ margin: "0 auto 1rem" }} />
            <p>Welcome! Ask me anything about the loaded policies.</p>
          </div>
        )}
        {chat.map((turn, idx) => {
          const dir = getDirection(turn.text);
          return (
            <article key={idx} className={`bubble ${turn.role} ${dir}`}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                {turn.role === "user" ? <User size={14} /> : <Bot size={14} />}
                <strong>{turn.role === "user" ? "You" : "Assistant"}</strong>
              </div>

              <div className="markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {turn.text || (busy && idx === chat.length - 1 ? "..." : "")}
                </ReactMarkdown>
              </div>

              {turn.sources && turn.sources.length > 0 && (
                <details>
                  <summary>
                    Sources ({turn.sources.length})
                  </summary>
                  <ul>
                    {turn.sources.map((s, i) => (
                      <li key={i}>
                        <div style={{ fontWeight: 600, marginBottom: "0.25rem", color: "var(--primary)" }}>
                          {s.page_number ? `Page ${s.page_number}` : "Page unknown"}
                        </div>
                        <p>{s.content}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          );
        })}
        <div ref={chatEndRef} />
      </section>

      <footer className="panel" style={{ marginTop: "auto", marginBottom: 0 }}>
        <form onSubmit={handleAsk} className="row">
          <input
            placeholder="Ask a policy question..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={busy}
          />
          <button type="submit" disabled={!canAsk}>
            {busy ? <div className="spinner" /> : <Send size={18} />}
            <span>{busy ? "Thinking..." : "Send"}</span>
          </button>
        </form>
      </footer>

      <style jsx>{`
        .spinner {
          width: 18px;
          height: 18px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </main>
  );
}
