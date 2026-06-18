import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ServerMessage,
  GameStateMsg,
  ChatMessage,
} from "./types";

export interface GameConnection {
  connected: boolean;
  playerId: string | null;
  playerName: string | null;
  state: GameStateMsg | null;
  chat: ChatMessage[];
  sendChat: (text: string) => void;
  setName: (name: string) => void;
  warpUp: () => void;
  warpDown: () => void;
  togglePause: () => void;
  // Launch pipeline
  acceptContract: (id: string) => void;
  planContract: (id: string, windowIndex: number) => void;
  assignCraft: (id: string, craftName: string) => void;
  setLaunch: (id: string, siteId: string, launchTime: number) => void;
  runOperation: (id: string, op: string) => void;
  cancelTask: (id: string, taskId: string) => void;
  correctIssue: (id: string, issueId: string) => void;
  launchContract: (id: string) => void;
}

// Connects to the FastAPI WebSocket (proxied through Vite at /ws in dev).
export function useGameSocket(): GameConnection {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [playerName, setPlayerName] = useState<string | null>(null);
  const [state, setState] = useState<GameStateMsg | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([]);

  useEffect(() => {
    let closed = false;
    let reconnectTimer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) reconnectTimer = window.setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as ServerMessage;
        switch (msg.type) {
          case "welcome":
            setPlayerId(msg.playerId);
            setPlayerName(msg.name);
            break;
          case "state":
            setState(msg);
            break;
          case "chat":
            setChat(msg.messages);
            break;
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  const send = useCallback((payload: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  return {
    connected,
    playerId,
    playerName,
    state,
    chat,
    sendChat: (text) => send({ action: "chat", text }),
    setName: (name) => {
      setPlayerName(name);
      send({ action: "setName", name });
    },
    warpUp: () => send({ action: "warpUp" }),
    warpDown: () => send({ action: "warpDown" }),
    togglePause: () => send({ action: "togglePause" }),
    acceptContract: (id) => send({ action: "acceptContract", id }),
    planContract: (id, windowIndex) => send({ action: "planContract", id, windowIndex }),
    assignCraft: (id, craftName) => send({ action: "assignCraft", id, craftName }),
    setLaunch: (id, siteId, launchTime) => send({ action: "setLaunch", id, siteId, launchTime }),
    runOperation: (id, op) => send({ action: "runOperation", id, op }),
    cancelTask: (id, taskId) => send({ action: "cancelTask", id, taskId }),
    correctIssue: (id, issueId) => send({ action: "correctIssue", id, issueId }),
    launchContract: (id) => send({ action: "launchContract", id }),
  };
}
