import "./explore-marks.css";

export function Search() {
  return (
    <svg className="workmark ex-mark ex-search" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <g className="ex-folder">
        <path d="M2.3 7.4V5.9c0-.7.5-1.2 1.2-1.2h3.7l1.7 2h6.8c.8 0 1.4.6 1.4 1.4v8.8c0 .8-.6 1.4-1.4 1.4h-12c-.8 0-1.4-.6-1.4-1.4V7.4Z" />
        <path d="M2.8 8.7h4.5M4.7 15.7h3" />
      </g>
      <g className="ex-scan-x"><g className="ex-scan-y"><g className="ex-lens">
        <path d="m13.8 14.3 4.6 4.6" strokeWidth="3.7" />
        <circle className="ex-surface" cx="10" cy="10.5" r="5.5" strokeWidth="1.85" />
        <circle cx="10" cy="10.5" r="4.8" fill="currentColor" fillOpacity=".12" stroke="none" />
        <path d="M6.8 9.5c.3-1.1 1-1.9 2.1-2.2" strokeWidth="1.25" opacity=".7" />
        <path className="ex-hit" d="m10.7 8 .8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8Z" fill="currentColor" stroke="none" />
      </g></g></g>
    </svg>
  );
}

function OrbitArc({ front = false }: { front?: boolean }) {
  const arc = front ? "M9.2 0a9.2 6.44 0 0 1-18.4 0" : "M-9.2 0a9.2 6.44 0 0 1 18.4 0";
  return (
    <g className={front ? "ex-front" : "ex-back"} transform="translate(12 12) rotate(-25)">
      <path d={arc} strokeWidth=".95" opacity={front ? ".4" : ".26"} />
      <g className="ex-depth" transform="scale(1 .7)">
        <g className="ex-orbit">
          <g transform="translate(9.2 0)">
            <g className="ex-stabilizer">
              {/* Undo the orbit's projection so the Moon stays round. */}
              <g className="ex-moon" transform="scale(1 1.42857)" stroke="none">
                <circle className="ex-moon-disc" r="2.7" strokeWidth=".55" />
                <path className="ex-moon-shade" d="M1.4-2.3A2.7 2.7 0 0 1-1.2 2.42C.25 2.53 1.47 1.68 1.87.5C2.2-.53 2.06-1.53 1.4-2.3Z" />
                <circle cx="-.8" cy="-.83" r=".73" />
                <circle cx=".35" cy=".92" r=".44" />
              </g>
            </g>
          </g>
        </g>
      </g>
    </g>
  );
}

export function Web() {
  return (
    <svg className="workmark ex-mark ex-web" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <OrbitArc />
      <circle className="ex-surface" cx="12" cy="12" r="7.4" strokeWidth="1.65" />
      <circle cx="12" cy="12" r="6.65" fill="currentColor" fillOpacity=".09" stroke="none" />
      <g strokeWidth="1.15">
        <path opacity=".64" d="M5.7 8.6q6.3 3 12.6 0M5.1 14.5q6.9 3.1 13.8 0" />
        <path className="ex-meridian" d="M12 4.6C6.4 7.8 6.4 16.2 12 19.4" />
        <path className="ex-meridian ex-meridian-next" d="M12 4.6C17.6 7.8 17.6 16.2 12 19.4" />
      </g>
      <OrbitArc front />
    </svg>
  );
}
