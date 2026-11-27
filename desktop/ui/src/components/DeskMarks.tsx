import type { ReactNode } from "react";
import "./desk-marks.css";

function DeskMark({ children }: { children: ReactNode }) {
  return <svg className="workmark dk-mark" viewBox="0 0 24 24" width="100%" height="100%"
    aria-hidden="true" focusable="false">{children}</svg>;
}

export function Write() {
  return (
    <DeskMark>
      <path className="dk-ink" pathLength="100"
        d="M3 17.4Q4.1 14.2 5.4 17.4T7.8 17.4T10.2 17.4T12.6 17.4" />
      <circle className="dk-period" cx="14.6" cy="17.4" r="1" />
      <path className="dk-ink-fleck" d="m16.8 14.6.9-1.2m.5 3.4 1.7-.4" />
      <g className="dk-pencil">
        <path className="dk-tinted" d="m3 17.4.45-4.05 5.1-9.1a1.1 1.1 0 0 1 1.5-.4l1.25.7a1.1 1.1 0 0 1 .4 1.5L6.6 15.1Z" />
        <path d="m3.6 13.4 2.8 1.55M7.8 5.8l3.05 1.7" />
      </g>
    </DeskMark>
  );
}

export function Command() {
  return (
    <DeskMark>
      <g className="dk-terminal">
        <rect className="dk-tinted" x="2.1" y="3.8" width="19.8" height="16.4" rx="3" />
        <path d="M2.6 8.6h18.8" opacity=".6" />
        <path d="M5.2 6.3h.25m2.2 0h.25" />
        <g className="dk-command-line">
          <path d="m5.1 11.7 2.3 2.2-2.3 2.2" />
          <path className="dk-key" d="M9.9 14h1.25" />
          <path className="dk-key dk-key-two" d="M13.2 14h1.25" />
          <path className="dk-key dk-key-three" d="M16.5 14h1.25" />
          <path className="dk-caret" d="M9.9 12.7v2.6" />
        </g>
        <path className="dk-enter" d="M18 13.3v3.1h-5.2m1.7-1.7-1.7 1.7 1.7 1.7" />
      </g>
    </DeskMark>
  );
}

export function Read() {
  return (
    <DeskMark>
      <g className="dk-sheet">
        <path className="dk-paper dk-tinted" d="M6 2.5H14.5L19.5 7.5V20Q19.5 21.5 18 21.5H6Q4.5 21.5 4.5 20V4Q4.5 2.5 6 2.5Z M14.5 2.5V6.4Q14.5 7.5 15.6 7.5H19.5" />
        <rect className="dk-highlight" x="6.4" y="9" width="11.2" height="3.3" rx="1.3" />
        <path d="M7.8 10.65h8.4M7.8 14.05h6.5M7.8 17.45h7.4" strokeWidth="1.3" />
      </g>
    </DeskMark>
  );
}

export function Plan() {
  return (
    <DeskMark>
      <g className="dk-board">
        <path className="dk-tinted" d="M8.5 4.2H5.4a1.8 1.8 0 0 0-1.8 1.8v14a1.8 1.8 0 0 0 1.8 1.8h13.2a1.8 1.8 0 0 0 1.8-1.8V6a1.8 1.8 0 0 0-1.8-1.8h-3.1" />
        <rect className="dk-tinted" x="8.5" y="2.3" width="7" height="3.7" rx="1.5" />
        {[9.5, 13.85, 18.2].map((y, i) => (
          <g key={y} transform={`translate(0 ${y})`}>
            <g className={`dk-task dk-task-${i + 1}`}>
              <rect className="dk-box" x="6.3" y="-1.2" width="2.4" height="2.4" rx=".65" />
              <path className="dk-check" pathLength="1" d="m5.9-.1 1.25 1.45 2.65-2.9" />
              <path className="dk-rule" d={`M12 0h${i === 2 ? 3.2 : 5}`} />
            </g>
          </g>
        ))}
      </g>
    </DeskMark>
  );
}
