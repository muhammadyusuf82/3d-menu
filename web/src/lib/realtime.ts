/** WebSocket client with exponential-backoff reconnect. The server only sends "something changed" pings; data is refetched over REST. */
export function connectRealtime(handlers: { onChanged: () => void; onStatus: (online: boolean) => void }): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  let attempt = 0;
  let timer: number | undefined;

  const open = () => {
    if (stopped) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    try { ws = new WebSocket(`${proto}://${location.host}/ws`); } catch { schedule(); return; }
    ws.onopen = () => { attempt = 0; handlers.onStatus(true); handlers.onChanged(); };
    ws.onmessage = (e) => {
      try { if (JSON.parse(String(e.data)).type === 'changed') handlers.onChanged(); } catch { /* ignore */ }
    };
    ws.onclose = () => { handlers.onStatus(false); schedule(); };
    ws.onerror = () => { try { ws?.close(); } catch { /* ignore */ } };
  };
  const schedule = () => {
    if (stopped) return;
    const delay = Math.min(10000, 500 * 2 ** attempt++);
    timer = window.setTimeout(open, delay);
  };
  open();
  return () => { stopped = true; clearTimeout(timer); try { ws?.close(); } catch { /* ignore */ } };
}
