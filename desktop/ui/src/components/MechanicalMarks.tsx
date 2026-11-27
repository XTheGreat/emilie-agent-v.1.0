import "./mechanical-marks.css";

export function Connect() {
  return (
    <svg className="workmark mx-mark mx-connect" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path className="mx-cord" d="M1 16.8C1 13.2 2 12 5 12" />
      <g className="mx-plug">
        <path d="M9.3 10.2h3.9m-3.9 3.6h3.9" strokeWidth="1.9" />
        <path className="mx-shell" d="M8.8 8.2h1.4v7.6H8.8c-3 0-4.9-1.5-4.9-3.8s1.9-3.8 4.9-3.8Z" />
        <path d="M7.2 10.5v3" opacity=".45" strokeWidth="1.1" />
      </g>
      <g className="mx-socket">
        <rect className="mx-shell" x="17.4" y="6.1" width="4.5" height="11.8" rx="1.6" />
        <path d="M17.8 10.2h1.5m-1.5 3.6h1.5" strokeWidth="1.2" />
        <circle className="mx-socket-led" cx="19.7" cy="8.1" r=".75" />
      </g>
      <g className="mx-energy" transform="translate(17.4 10.2)">
        <path className="mx-gap-arc" d="M-3.6 0l1.2-.85.8 1.25L0 0" />
        <g className="mx-discharge">
          <path d="M0 0l-1.5-2.3-1.8.25-.85-2.1-3.2-1.05" />
          <path d="m-4.15-4.15.2-1.45-1.15-1.5" strokeWidth=".85" />
        </g>
        <g className="mx-contact">
          <ellipse rx="2.4" ry="1.8" fill="currentColor" opacity=".4" stroke="none" />
          <circle r="1.15" fill="#fff6ce" strokeWidth=".75" />
        </g>
        <path className="mx-grain mx-streak" d="M.45.25Q-1.4.65-3.5-.55Q-1.05-.75.45.25Z" />
        <path className="mx-grain mx-fleck" d="M.1.65Q-1.05-.8-.8-2.5Q.55-.75.1.65Z" />
        <circle className="mx-grain mx-bead" r=".76" />
        <g transform="translate(0 3.6)">
          <g className="mx-contact mx-contact-lower">
            <ellipse rx="1.55" ry="1.25" fill="currentColor" opacity=".42" stroke="none" />
            <circle r=".76" fill="#fff6ce" strokeWidth=".55" />
          </g>
          <path className="mx-grain mx-spall" d="M.6-.4Q.1 1.05-1.7 1.75Q-1.15.1.6-.4Z" />
        </g>
      </g>
    </svg>
  );
}

export function Tool() {
  return (
    <svg className="workmark mx-mark mx-tool" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <g className="mx-torque">
        <g className="mx-jaw mx-jaw-left">
          <path d="m11.9 4.8-.1 1.5 2.6 5.1 1.7 3.8" strokeWidth="1.9" />
          <path d="m16.1 15.2 1.7 4.6" strokeWidth="3.2" />
        </g>
        <g className="mx-jaw mx-jaw-right">
          <path d="m16.9 4.8.1 1.5-2.6 5.1-1.8 3.8" strokeWidth="1.9" />
          <path d="m12.6 15.2-1.7 4.6" strokeWidth="3.2" />
        </g>
        <circle className="mx-shell" cx="14.4" cy="11.4" r="1.3" strokeWidth="1.3" />
      </g>
      <g className="mx-nut">
        <path className="mx-shell" d="m14.4 2.7 2.5 1.45v2.9l-2.5 1.45-2.5-1.45v-2.9Z" strokeWidth="1.4" />
        <circle cx="14.4" cy="5.6" r=".9" className="mx-solid" />
      </g>
      <path className="mx-torque-ticks" d="m4.6 10.4-1.7-.7m2.3 3H2.9" strokeWidth="1.1" />
    </svg>
  );
}

export function Helper() {
  return (
    <svg className="workmark mx-mark mx-helper" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <ellipse className="mx-shadow mx-solid" cx="12" cy="21.4" rx="5.4" ry=".85" />
      <g className="mx-hop">
        <g className="mx-aerial">
          <path d="m12 9-.9-3" strokeWidth="1.4" />
          <circle className="mx-solid" cx="10.9" cy="5.1" r="1.25" />
        </g>
        <path className="mx-arm-left" d="m6.9 14.3-2.5 1.5" strokeWidth="2" />
        <path className="mx-arm-right" d="m17.1 14.3 2.4.9" strokeWidth="2" />
        <path d="m9 18.4-.4 1.6m6.4-1.6.6 1.6" strokeWidth="2.4" />
        <rect className="mx-shell" x="6.1" y="8.4" width="11.8" height="10.2" rx="3.4" />
        <rect className="mx-solid" x="7.7" y="10.5" width="8.6" height="4.9" rx="2.15" />
        <g className="mx-eyes">
          <path d="M10.1 12.45v1m3.8-1v1" stroke="var(--bg-000)" strokeWidth="1.5" />
        </g>
        <path d="M10.7 16.65q1.3 1 2.6 0" strokeWidth="1.05" />
      </g>
      <path className="mx-landing" d="m5.5 19.5-2-1m15 1 2-1" strokeWidth="1.15" />
    </svg>
  );
}
