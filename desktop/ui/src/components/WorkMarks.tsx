// Emilie's working marks: the flower, and one mark per kind of work (pencil, globe, wrench, terminal, …), all in one
// 20×20 box. Every moving part is its own little layer that only moves (transform) and fades (opacity), so the GPU runs
// the motion by itself and it stays smooth even while the page is busy. The motion lives in styles.css ("working marks").
// Each part fills the whole box and draws at its place in the 20-unit grid, so a CSS transform-origin of
// (x*5)% (y*5)% is the point (x, y) and a translation of u units is u*0.05em.
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/util";

export type WorkKind = "write" | "plan" | "command" | "helper" | "tool" | "read" | "search" | "web" | "connect";
type Vars = React.CSSProperties & Record<`--${string}`, string | number>;

function Svg({ children }: { children: React.ReactNode }) {
  return <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">{children}</svg>;
}

/** One part: a layer as big as the mark (its drawing sits where it belongs in the grid). */
function P({ c, s, children }: { c?: string; s?: Vars; children?: React.ReactNode }) {
  return <i className={c ? "p " + c : "p"} style={s}>{children}</i>;
}

// ------------------------------------------------------------------ the flower
/** Five petals round a heart, turning slowly. Waiting: one petal at a time wakes, stretches and dozes off again.
 *  Thinking: a ripple runs round, each petal stretching out like rubber and wobbling back. Replying: the same, brisk,
 *  and the whole flower wobbles like jelly. The slow turn is the same in every mood, so a change of mood never jumps. */
export function Bloom({ mode = "think", size }: { mode?: "wait" | "think" | "reply"; size?: number }) {
  return (
    <span className={`mk bloom bl-${mode}`} style={size ? { fontSize: size } : undefined} aria-hidden="true">
      <P c="bl-turn">
        {[0, 1, 2, 3, 4].map((i) => (
          <P key={i} s={{ transform: `rotate(${i * 72}deg)` }}>
            <P c="bl-petal" s={{ "--i": i }}><Svg><ellipse className="f" cx="10" cy="5.15" rx="2.3" ry="3.55" /></Svg></P>
          </P>
        ))}
        <P c="bl-core"><Svg><circle className="f" cx="10" cy="10" r="1.5" /></Svg></P>
      </P>
    </span>
  );
}

// ------------------------------------------------------------------ one mark per kind of work
/** Writing a file: the pencil drops onto the line (squashing a little), scribbles a wavy line as it goes, taps a full
 *  stop, lifts off, and springs back to the start while the ink fades. */
function Write() {
  return (
    <>
      <P c="wr-ink wr-i1"><Svg><path d="M2.9 15C3.5 15 3.4 15.6 4 15.6C4.6 15.6 4.5 14.4 5.1 14.4" strokeWidth="1.2" /></Svg></P>
      <P c="wr-ink wr-i2"><Svg><path d="M5.1 14.4C5.7 14.4 5.6 15.6 6.2 15.6C6.8 15.6 6.7 14.4 7.3 14.4" strokeWidth="1.2" /></Svg></P>
      <P c="wr-ink wr-i3"><Svg><path d="M7.3 14.4C7.9 14.4 7.8 15.6 8.4 15.6C9 15.6 8.9 14.4 9.5 14.4" strokeWidth="1.2" /></Svg></P>
      <P c="wr-ink wr-i4"><Svg><path d="M9.5 14.4C10.1 14.4 10 15.6 10.6 15.6C11.2 15.6 11.1 14.4 11.7 14.4C12 14.4 12.1 15 12.2 15.4" strokeWidth="1.2" /></Svg></P>
      <P c="wr-dot fx"><Svg><circle className="f" cx="13.6" cy="15.35" r=".72" /></Svg></P>
      <P c="wr-pen"><Svg>
        <g transform="translate(2.4 15.4) scale(1.2) translate(-2.4 -15.4)">
          <path className="t" d="M4.87 14.53L8.48 10.52L6.62 8.84L3.01 12.86Z" strokeWidth="1" />
          <path d="M2.4 15.4L4.87 14.53L3.01 12.86Z" strokeWidth=".9" />
          <path className="f" d="M2.4 15.4L3.25 15.09L2.62 14.52Z" />
          <path className="f" d="M8.48 10.52L9.65 9.14L7.86 7.54L6.62 8.84Z" fillOpacity=".8" />
        </g>
      </Svg></P>
    </>
  );
}

/** On the web: a globe spinning (its meridians sweep across), wobbling softly like jelly, with a little satellite on
 *  a tilted orbit that grows as it comes round the front and fades as it goes behind. */
function Web() {
  return (
    <>
      <P c="gl-body">
        <P><Svg>
          <circle cx="10" cy="10" r="6.6" />
          <path className="dim" d="M3.4 10Q10 12.3 16.6 10" />
          <path className="dim" d="M4.47 6.4Q10 8.1 15.53 6.4" />
          <path className="dim" d="M4.47 13.6Q10 15.3 15.53 13.6" />
        </Svg></P>
        {[0, 1, 2, 3].map((k) => (
          <P key={k} c="gl-mer" s={{ "--k": k }}><Svg><path d="M10 3.4A6.6 6.6 0 0 1 10 16.6" strokeWidth="1.1" /></Svg></P>
        ))}
      </P>
      <P c="gl-path"><Svg><ellipse cx="10" cy="10" rx="9.2" ry="2.9" transform="rotate(-20 10 10)" strokeWidth=".9" /></Svg></P>
      <P c="gl-orbit"><P c="gl-ox"><P c="gl-oy"><Svg><circle className="f" cx="10" cy="10" r="1.2" /></Svg></P></P></P>
    </>
  );
}

/** Using a tool: pliers (tang). The handles snap together and the jaws bite a nut, which squashes like rubber; the pliers
 *  yank it to and fro (the long handles swing wide, settling like a spring), then let go: the jaws spring open past
 *  their rest and the nut bounces back into shape. */
function Tool() {
  return (
    <P c="tg-wig">
      <P c="tg-arm tg-r"><Svg>
        <path d="M10 8.6L7.7 2.7" strokeWidth="2.1" />
        <path d="M10 8.6L12.585 13.77" strokeWidth="1.3" />
        <path d="M12.585 13.77L14.7 18" strokeWidth="2.8" opacity=".6" />
      </Svg></P>
      <P c="tg-arm tg-l"><Svg>
        <path d="M10 8.6L12.3 2.7" strokeWidth="2.1" />
        <path d="M10 8.6L7.415 13.77" strokeWidth="1.3" />
        <path d="M7.415 13.77L5.3 18" strokeWidth="2.8" opacity=".6" />
      </Svg></P>
      <P><Svg><circle className="t" cx="10" cy="8.6" r="1.05" strokeWidth="1" /></Svg></P>
      <P c="tg-nut"><Svg><path className="t" d="M11.256 2.125L10 1.4L8.744 2.125V3.575L10 4.3L11.256 3.575Z" strokeWidth="1" /></Svg></P>
    </P>
  );
}

/** Running a command: three keys pop up one by one (each squashes and springs into shape) with the caret hopping
 *  after them; Enter sends the line up and away and the window wobbles like jelly. */
function Command() {
  return (
    <>
      <P c="cm-win"><Svg>
        <rect className="t" x="2.2" y="3.6" width="15.6" height="12.8" rx="2.6" />
        <path className="dim" d="M2.2 7H17.8" />
        <circle className="f dim" cx="4.35" cy="5.3" r=".55" />
        <circle className="f dim" cx="5.95" cy="5.3" r=".55" />
        <circle className="f dim" cx="7.55" cy="5.3" r=".55" />
        <path d="M4.8 9.6L6.6 11.4L4.8 13.2" />
      </Svg></P>
      <P c="cm-key cm-k1"><Svg><path d="M8.2 11.4H9.6" strokeWidth="1.7" /></Svg></P>
      <P c="cm-key cm-k2"><Svg><path d="M10.4 11.4H11.8" strokeWidth="1.7" /></Svg></P>
      <P c="cm-key cm-k3"><Svg><path d="M12.6 11.4H14" strokeWidth="1.7" /></Svg></P>
      <P c="cm-caret"><Svg><rect className="f" x="7.85" y="9.9" width=".95" height="3" rx=".4" /></Svg></P>
    </>
  );
}

/** Planning: the boxes tick one after another (the box squashes, the tick bounces in with a twist, its line dims as
 *  done), then they clear in the same order and start again. */
function Plan() {
  const rows = [5.2, 10, 14.8];
  return (
    <>
      {rows.map((y, k) => (
        <P key={"b" + k} c="pl-box" s={{ "--k": k, transformOrigin: `23% ${y * 5}%` }}><Svg><circle cx="4.6" cy={y} r="2.05" strokeWidth="1.15" /></Svg></P>
      ))}
      {rows.map((y, k) => (
        <P key={"l" + k} c="pl-bar" s={{ "--k": k }}><Svg><path d={`M8.6 ${y}H${k === 1 ? 14.4 : 16.4}`} strokeWidth="1.3" /></Svg></P>
      ))}
      {rows.map((y, k) => (
        <P key={"c" + k} c="pl-check" s={{ "--k": k, transformOrigin: `23% ${y * 5}%` }}><Svg>
          <circle className="f" cx="4.6" cy={y} r="2.05" fillOpacity=".24" />
          <path d={`M3.65 ${y + 0.05}L4.35 ${y + 0.8}L5.7 ${y - 0.85}`} strokeWidth="1.3" />
        </Svg></P>
      ))}
    </>
  );
}

/** A helper at work: a little robot hops, crouching before the jump, stretching as it takes off, squashing as it lands;
 *  its antenna whips behind each move, its light pulses, it blinks now and then, and its shadow shrinks as it rises. */
function Helper() {
  return (
    <>
      <P c="rb-shadow"><Svg><ellipse className="f" cx="10" cy="18.4" rx="4.2" ry=".8" fillOpacity=".3" /></Svg></P>
      <P c="rb-hop"><P c="rb-squash">
        <P c="rb-ant">
          <Svg><path d="M10 7.6V4.9" strokeWidth="1.15" /></Svg>
          <P c="rb-led"><Svg><circle className="f" cx="10" cy="4" r="1.15" /></Svg></P>
        </P>
        <P><Svg>
          <rect className="t" x="4.8" y="7.6" width="10.4" height="8" rx="2.8" />
          <path d="M3.55 10.6V12.6M16.45 10.6V12.6" strokeWidth="1.3" />
          <path d="M8.7 13.65Q10 14.5 11.3 13.65" strokeWidth="1" />
        </Svg></P>
        <P c="rb-eyes"><Svg><circle className="f" cx="8.2" cy="11.3" r="1.05" /><circle className="f" cx="11.8" cy="11.3" r="1.05" /></Svg></P>
      </P></P>
    </>
  );
}

/** Reading: a highlight hops down the page line by line (stretching as it jumps, squashing as it lands), each line lights
 *  up as it is read, the page sways gently, and at the end it turns over with a springy flip. */
function Read() {
  const lines: [number, number][] = [[8.8, 13.4], [11, 12.4], [13.2, 13.4], [15.4, 10.8]];
  return (
    <P c="rd-page">
      <P><Svg>
        <path className="t" d="M5 2.6H11.8L15.4 6.2V17.4H5Z" />
        <path d="M11.8 2.6V6.2H15.4" strokeWidth="1" />
      </Svg></P>
      <P c="rd-hi fx"><Svg><rect className="f" x="6.3" y="7.7" width="8" height="2.2" rx="1.1" fillOpacity=".3" /></Svg></P>
      {lines.map(([y, x2], k) => (
        <P key={k} c="rd-line" s={{ "--k": k }}><Svg><path d={`M7.2 ${y}H${x2}`} strokeWidth="1.15" /></Svg></P>
      ))}
    </P>
  );
}

/** Searching the project: the magnifier glides in a figure of eight over scattered files; at each end it stops on a
 *  file, which flashes, and the lens zooms in on it with a springy pop. */
function Search() {
  return (
    <>
      <P><Svg>
        {[[7.2, 5.4], [12.8, 5.4], [10, 9.3], [7.2, 13.4], [12.8, 13.4]].map(([x, y], i) => (
          <circle key={i} className="f" cx={x} cy={y} r=".6" fillOpacity=".3" />
        ))}
      </Svg></P>
      <P c="sr-dot sr-d1"><Svg><circle className="f" cx="4.6" cy="9.3" r=".75" /></Svg></P>
      <P c="sr-dot sr-d2"><Svg><circle className="f" cx="15.4" cy="9.3" r=".75" /></Svg></P>
      <P c="sr-x"><P c="sr-y"><P c="sr-zoom"><Svg>
        <circle cx="10" cy="9.3" r="3.3" strokeWidth="1.35" />
        <path className="dim" d="M8.2 7.9A2.3 2.3 0 0 1 10.1 7.1" strokeWidth=".9" />
        <path d="M12.4 11.7L14.7 14" strokeWidth="2" />
      </Svg></P></P></P>
    </>
  );
}

/** Connecting tools: the plug shoots into the wall socket, overshoots and bounces (the socket squashes, sparks fly, it
 *  lights up), stays a moment, then is pulled out again; its cord stretches and slackens like rubber as it goes. */
function Connect() {
  return (
    <>
      <P c="cn-cord"><Svg><path d="M5 10C3.6 10 2.5 11.8 0.4 11.6" strokeWidth="1.2" /></Svg></P>
      <P c="cn-sock"><Svg>
        <rect className="t" x="14.4" y="4.2" width="3" height="11.6" rx="1.2" />
        <path d="M14.4 8.6H15.6M14.4 11.4H15.6" strokeWidth="1.2" />
      </Svg></P>
      <P c="cn-glow fx"><Svg><rect className="f" x="14.4" y="4.2" width="3" height="11.6" rx="1.2" fillOpacity=".5" /></Svg></P>
      <P c="cn-plug"><Svg>
        <rect className="t" x="5" y="6.3" width="4.4" height="7.4" rx="1.8" />
        <path d="M9.4 8.6H12.4M9.4 11.4H12.4" strokeWidth="1.35" />
      </Svg></P>
      <P c="cn-spark fx"><Svg>
        <path d="M14 7L13.6 5.8M14 13L13.6 14.2" strokeWidth="1" />
        <circle className="f" cx="14.4" cy="10" r=".95" />
      </Svg></P>
    </>
  );
}

const MARKS: Record<WorkKind, () => React.ReactElement> = {
  write: Write, web: Web, tool: Tool, command: Command, plan: Plan, helper: Helper, read: Read, search: Search, connect: Connect,
};

/** The mark for a kind of work. */
export function WorkMark({ kind, size }: { kind: WorkKind; size?: number }) {
  const Body = MARKS[kind] || Tool;
  return <span className={`mk mk-${kind}`} style={size ? { fontSize: size } : undefined} aria-hidden="true"><Body /></span>;
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
