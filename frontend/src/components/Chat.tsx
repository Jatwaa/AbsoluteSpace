import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  online: number;
  onSend: (text: string) => void;
}

export function Chat({ messages, online, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const submit = () => {
    const t = draft.trim();
    if (t) {
      onSend(t);
      setDraft("");
    }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <span>GLOBAL COMMS · ALL STATIONS</span>
        <span className="chat-online">● {online} online</span>
      </div>
      <div className="panel-body chat-log" ref={logRef}>
        {messages.map((m) => (
          <div className="chat-msg" key={m.id}>
            <span className={`who role-${m.role}`}>{m.author}</span>
            <span className="body">{m.text}</span>
          </div>
        ))}
      </div>
      <div className="chat-input-row">
        <input
          value={draft}
          placeholder="Broadcast to all stations…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
        />
        <button onClick={submit}>SEND</button>
      </div>
    </div>
  );
}
