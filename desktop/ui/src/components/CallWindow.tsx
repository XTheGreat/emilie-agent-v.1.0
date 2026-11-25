// The video call's little window, inside the app: what the camera sees, floating over the conversation like a call.
// The camera itself is read by the session's process (it also feeds Emilie); this window only shows its newest frame.
import { useEffect, useRef, useState } from "react";
import { post } from "@/lib/api";
import { useStore } from "@/lib/store";
import { X } from "./icons";

const W = 240;                                   // the window's width; the height follows the picture (4:3 until the first frame)
const POLL_MS = 150;

export function CallWindow({ wid }: { wid: string }) {
  const [src, setSrc] = useState("");
  const [ratio, setRatio] = useState(3 / 4);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [err, setErr] = useState("");
  const box = useRef<HTMLDivElement>(null);

  // the newest frame, one request at a time (a slow answer never piles requests up); resting while the app is hidden
  useEffect(() => {
    let dead = false, timer = 0;
    const tick = async () => {
      if (dead) return;
      if (!document.hidden) {
        try {
          const r = await post<{ b64?: string; w?: number; h?: number; error?: string }>("/api/session/call/frame", { wid });
          if (dead) return;
          if (r.b64) {
            setSrc(`data:image/jpeg;base64,${r.b64}`);
            if (r.w && r.h) setRatio(r.h / r.w);
            setErr("");
          } else if (r.error) setErr(r.error);
        } catch { /* the session is busy or gone: try again */ }
      }
      timer = window.setTimeout(tick, POLL_MS);
    };
    tick();
    return () => { dead = true; clearTimeout(timer); };
  }, [wid]);

  // drag by the title bar, kept inside the window
  const drag = (e: React.PointerEvent) => {
    const el = box.current;
    if (!el || (e.target as HTMLElement).closest("button")) return;
    const r = el.getBoundingClientRect();
    const dx = e.clientX - r.left, dy = e.clientY - r.top;
    const move = (m: PointerEvent) => setPos({
      x: Math.max(4, Math.min(window.innerWidth - r.width - 4, m.clientX - dx)),
      y: Math.max(40, Math.min(window.innerHeight - r.height - 4, m.clientY - dy)),
    });
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div ref={box} role="dialog" aria-label="Video call"
      className="fixed z-40 overflow-hidden rounded-[10px] border border-border-400 bg-bg-200 shadow-[0_6px_24px_rgba(0,0,0,0.4)] animate-pop"
      style={{ width: W, ...(pos ? { left: pos.x, top: pos.y } : { right: 24, bottom: 150 }) }}>
      <div onPointerDown={drag} className="flex h-[24px] cursor-grab items-center gap-1.5 border-b border-border-300 px-2 text-[11px] text-text-200 active:cursor-grabbing">
        <span className="h-[6px] w-[6px] rounded-full bg-danger animate-pulse" />
        <span className="flex-1 truncate">Video call</span>
        <button onClick={() => useStore.getState().setCall(wid, false)} aria-label="End the video call" title="End the video call"
          className="flex h-[18px] w-[18px] items-center justify-center rounded text-text-300 hover:bg-hover hover:text-text-000"><X size={12} /></button>
      </div>
      <div className="relative bg-black" style={{ aspectRatio: `${1 / ratio}` }}>
        {src
          ? <img src={src} alt="" draggable={false} className="h-full w-full object-cover" style={{ transform: "scaleX(-1)" }} />
          : <div className="flex h-full items-center justify-center px-3 text-center text-[11px] text-text-400">{err || "Starting the camera…"}</div>}
      </div>
    </div>
  );
}
