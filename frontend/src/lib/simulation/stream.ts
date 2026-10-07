import { useSim } from "./store";

/**
 * Real-time channel to the simulation. Commands go over REST; state arrives here.
 * Reconnects with backoff; re-sends the robot focus after reconnecting.
 */
let socket: WebSocket | null = null;
let retry = 0;
let focused: string | null = null;
let started = false;

function url(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/simulation`;
}

function connect() {
  const store = useSim.getState();
  store.setConnection("connecting");
  const ws = new WebSocket(url());
  socket = ws;
  ws.onopen = () => {
    retry = 0;
    useSim.getState().setConnection("open");
    if (focused) ws.send(JSON.stringify({ type: "focus", robot_id: focused }));
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    const s = useSim.getState();
    if (msg.type === "static") s.setStatic(msg.map, msg.status, msg.version);
    else if (msg.type === "snapshot") s.applySnapshot(msg);
  };
  ws.onclose = () => {
    useSim.getState().setConnection("closed");
    socket = null;
    const delay = Math.min(8000, 500 * 2 ** retry++);
    window.setTimeout(connect, delay);
  };
  ws.onerror = () => ws.close();
}

export function startStream() {
  if (started) return;
  started = true;
  connect();
}

export function setFocus(robotId: string | null) {
  focused = robotId;
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "focus", robot_id: robotId }));
}
