"use client";

import { FormEvent, useMemo, useState } from "react";

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

export default function PdfChat() {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [chat, setChat] = useState<ChatTurn[]>([]);

  const canAsk = useMemo(() => prompt.trim().length > 0 && !busy, [prompt, busy]);

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

  return (
    <main className="shell">
      <section className="panel">
        <h1>Policy Navigator</h1>
        <p className="status">This chat is connected to the indexed PDF: Book and policies.pdf</p>

        <form onSubmit={handleAsk} className="row">
          <input
            placeholder="Ask a policy question..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <button type="submit" disabled={!canAsk}>{busy ? "Streaming..." : "Send"}</button>
        </form>
      </section>

      <section className="chatlog">
        {chat.map((turn, idx) => (
          <article key={idx} className={`bubble ${turn.role}`}>
            <strong>{turn.role === "user" ? "You" : "Assistant"}</strong>
            <p>{turn.text}</p>
            {turn.sources && turn.sources.length > 0 && (
              <details>
                <summary>Sources</summary>
                <ul>
                  {turn.sources.map((s, i) => (
                    <li key={i}>
                      <strong>{s.page_number ? `Page ${s.page_number}` : "Page unknown"}:</strong>{" "}
                      {s.content.slice(0, 250)}...
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </article>
        ))}
      </section>
    </main>
  );
}
