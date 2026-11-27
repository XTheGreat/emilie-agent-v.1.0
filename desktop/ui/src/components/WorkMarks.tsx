import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { VoiceClip } from "@/lib/types";
import { cn } from "@/lib/util";
import { Command, Plan, Read, Write } from "./DeskMarks";
import { Search, Web } from "./ExploreMarks";
import { Connect, Helper, Tool } from "./MechanicalMarks";

export type WorkKind = "write" | "plan" | "command" | "helper" | "tool" | "read" | "search" | "web" | "connect";
type BloomMode = "wait" | "think" | "reply";

export function Bloom({ mode = "think", size }: { mode?: BloomMode; size?: number }) {
  return (
    <span className={`activity-mark bloom bl-${mode}`} style={{ fontSize: size }} aria-hidden="true">
      <svg className="workmark" viewBox="0 0 24 24" focusable="false">
        <g className="bl-body">
          <g className="bl-turn">
            {[0, 1, 2, 3, 4].map((i) => (
              <g key={i} transform={`rotate(${i * 72} 12 12)`}>
                <g className="bl-petal" style={{ "--i": i } as CSSProperties}>
                  <path fill="currentColor" d="M11.8 10.5C10.2 10.1 8.3 7.1 8.8 4.9C9.2 2.8 11.6 1.8 13.5 2.7C15.4 3.6 15.9 5.7 15 7.5C14.3 9 13 10.2 11.8 10.5Z" />
                  <path className="bl-fold" d="M10.5 4.6C9.9 6 10.5 7.6 11.7 8.8C11.2 7.6 10.9 6.1 11.3 5.1C11.6 4.3 10.9 4 10.5 4.6Z" />
                </g>
              </g>
            ))}
          </g>
          <circle className="bl-heart" cx="12" cy="12" r="2.15" />
        </g>
        {mode === "think" && (
          <g className="bl-orbit" fill="none" stroke="currentColor" strokeLinecap="round">
            <path d="M3 5.6A11 11 0 0 1 7.2 2.2" opacity=".55" strokeWidth="1.2" />
            <circle cx="9.3" cy="1.45" r=".85" fill="currentColor" stroke="none" />
          </g>
        )}
        {mode === "reply" && (
          <g className="bl-pollen">
            <path d="m19.8 1.2.55 1.6 1.6.6-1.6.55-.55 1.65-.55-1.65-1.6-.55 1.6-.6Z" />
            <circle cx="22.2" cy="6.1" r=".7" />
          </g>
        )}
      </svg>
    </span>
  );
}

const MARKS: Record<WorkKind, () => React.ReactElement> = {
  write: Write, web: Web, tool: Tool, command: Command, plan: Plan, helper: Helper, read: Read, search: Search, connect: Connect,
};

export function VoiceRibbon({ clip }: { clip?: VoiceClip }) {
  const envelope = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const layer = envelope.current;
    if (!layer || !clip?.levels.length) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const duration = clip.levels.length * clip.intervalMs;
    let playback: Animation | undefined;
    const sync = () => {
      playback?.cancel();
      const elapsed = Date.now() - clip.startedAt;
      if (reduced.matches || elapsed >= duration) return;
      // One set of evenly spaced transforms per clip. Seeking keeps the meter
      // in time when the user comes back to this chat halfway through a line.
      const frames = clip.levels.map(level => ({ transform: `scaleY(${.06 + .94 * level})` }));
      frames.push({ transform: "scaleY(.06)" });
      playback = layer.animate(frames, { duration, fill: "both" });
      playback.currentTime = elapsed;
    };
    sync();
    reduced.addEventListener("change", sync);
    return () => {
      reduced.removeEventListener("change", sync);
      playback?.cancel();
    };
  }, [clip]);
  return (
    <span className="voice-ribbon" data-measured={clip?.levels.length ? true : undefined} aria-hidden="true">
      <span ref={envelope} className="voice-ribbon-envelope">
        {[9, 15, 20, 17, 11].map((height, i) => (
          <i key={height} style={{ height, animationDelay: `-${i * .19}s` }} />
        ))}
      </span>
    </span>
  );
}

export function WorkMark({ kind, size }: { kind: WorkKind; size?: number }) {
  const Body = MARKS[kind] || Tool;
  return <span className={`activity-mark mk-${kind}`} style={{ fontSize: size }} aria-hidden="true"><Body /></span>;
}

// ------------------------------------------------------------------ swapping marks, and the working words
/** The place of the mark beside the working words. When the kind of work changes, the old mark shrinks away while the
 *  new one pops in with a spring; while it stays the same, the mark keeps its element, so its motion runs on unbroken. */
export function MarkSlot({ id, children }: { id: string; children: React.ReactNode }) {
  const [s, setS] = useState<{ cur: string; old: string | null }>({ cur: id, old: null });
  const drawn = useRef(new Map<string, React.ReactNode>());
  drawn.current.set(id, children);
  if (s.cur !== id) setS({ cur: id, old: s.cur });               // the old one leaves (same element, now leaving)
  useEffect(() => {
    if (!s.old) return;
    const t = window.setTimeout(() => setS((x) => (x.old ? { cur: x.cur, old: null } : x)), 220);
    return () => clearTimeout(t);
  }, [s.old]);
  return (
    <span className="mk-slot" aria-hidden="true">
      {s.old && s.old !== id && <span key={s.old} className="mk-out">{drawn.current.get(s.old)}</span>}
      <span key={id} className="mk-in">{children}</span>
    </span>
  );
}

/** Working words with a soft light sweeping over them. The light is a copy of the words in the bright colour, seen through
 *  a narrow window that slides across while the copy slides the other way (so it stays on the words): two moves the GPU
 *  runs by itself, where a moving gradient background would be repainted by the page every frame. */
export function Shimmer({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("shim", className)}>
      {children}
      <span className="shim-band" aria-hidden="true"><span className="shim-copy">{children}</span></span>
    </span>
  );
}
