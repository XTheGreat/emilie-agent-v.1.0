// Emilie's icon in the four styles of the terminal version: video, still image, ASCII (CLI) and pixel.
import { useEffect, useRef, useState } from "react";
import { media } from "@/lib/api";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/util";

export type IconMode = "video" | "image" | "ascii" | "pixel";

function useLogoUrls() {
  const logo = useStore((s) => s.settings.logo || "");
  const v = (String(logo.length) + logo.slice(-24)) + "_rev4";
  return { video: media("/media/logo", { v }), still: media("/media/logo-still", { v }) };
}

export function EmilieIcon({ size = 64, mode, className, ring = true }: { size?: number; mode?: IconMode; className?: string; ring?: boolean }) {
  const setting = useStore((s) => s.settings.desktop_icon) as IconMode | undefined;
  const fps = useStore((s) => Math.max(4, Math.min(30, Number(s.settings.fps) || 12)));
  const m: IconMode = mode || setting || "video";
  const urls = useLogoUrls();
  const [videoFailed, setVideoFailed] = useState(false);
  useEffect(() => setVideoFailed(false), [urls.video]);

  const box = cn("relative shrink-0 overflow-hidden select-none",
    ring && m !== "ascii" && "ring-1 ring-border-300", className);
  if (m === "image" || (m === "video" && videoFailed)) {
    return (
      <div className={box} style={{ width: size, height: size }}>
        <img src={urls.still} alt="Emilie" draggable={false} className="h-full w-full object-cover" />
      </div>
    );
  }
  if (m === "video") {
    return (
      <div className={box} style={{ width: size, height: size }}>
        <video key={urls.video} src={urls.video} autoPlay loop muted playsInline draggable={false}
          poster={urls.still} onError={() => setVideoFailed(true)} className="h-full w-full object-cover" />
      </div>
    );
  }
  return <CanvasIcon size={size} mode={m} fps={fps} className={box} src={urls.video} still={urls.still} />;
}

const RAMP = " .,:;-=+*cxoO0#%@";

function CanvasIcon({ size, mode, fps, className, src, still }: { size: number; mode: "ascii" | "pixel"; fps: number; className: string; src: string; still: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [useImg, setUseImg] = useState(false);
  const srcRef = useRef<HTMLVideoElement | HTMLImageElement | null>(null);

  useEffect(() => {
    const cv = canvas.current!;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.round(size * dpr);
    cv.height = Math.round(size * dpr);
    const ctx = cv.getContext("2d")!;
    const sample = document.createElement("canvas");
    const sctx = sample.getContext("2d", { willReadFrequently: true })!;
    const cols = mode === "ascii" ? Math.max(18, Math.min(72, Math.round(size / 5))) : Math.max(16, Math.min(48, Math.round(size / 3.2)));
    const rows = mode === "ascii" ? Math.round(cols * 0.55) : cols;
    sample.width = cols;
    sample.height = rows;
    let raf = 0;
    let last = 0;
    let visible = true;
    const io = new IntersectionObserver((e) => (visible = e[0]?.isIntersecting ?? true));
    io.observe(cv);

    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      if (!visible || document.hidden || t - last < 1000 / fps) return;
      last = t;
      const el = srcRef.current;
      if (!el) return;
      const w = (el as HTMLVideoElement).videoWidth || (el as HTMLImageElement).naturalWidth;
      const h = (el as HTMLVideoElement).videoHeight || (el as HTMLImageElement).naturalHeight;
      if (!w || !h) return;
      const side = Math.min(w, h);
      sctx.clearRect(0, 0, cols, rows);
      sctx.drawImage(el, (w - side) / 2, (h - side) / 2, side, side, 0, 0, cols, rows);
      if (mode === "pixel") {
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, cv.width, cv.height);
        ctx.drawImage(sample, 0, 0, cv.width, cv.height);
        return;
      }
      const data = sctx.getImageData(0, 0, cols, rows).data;
      let lo = 1, hi = 0;
      const lum = new Float32Array(cols * rows);
      for (let i = 0; i < cols * rows; i++) {
        const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2];
        const l = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
        lum[i] = l;
        if (l < lo) lo = l;
        if (l > hi) hi = l;
      }
      const span = Math.max(0.15, hi - lo);
      ctx.clearRect(0, 0, cv.width, cv.height);
      const cw = cv.width / cols, ch = cv.height / rows;
      ctx.font = `600 ${Math.ceil(ch * 1.05)}px "Cascadia Mono", Consolas, monospace`;
      ctx.textBaseline = "top";
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const i = y * cols + x;
          const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2];
          const sat = Math.max(r, g, b) - Math.min(r, g, b);
          if (lum[i] > 0.93 && sat < 26) continue;              // the white background: empty, like the terminal
          const n = (lum[i] - lo) / span;
          const c = RAMP[Math.max(1, Math.min(RAMP.length - 1, Math.round((1 - n * 0.75) * (RAMP.length - 1))))];
          ctx.fillStyle = `rgb(${Math.min(255, r * 1.08)},${Math.min(255, g * 1.08)},${Math.min(255, b * 1.08)})`;
          ctx.fillText(c, x * cw, y * ch);
        }
      }
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, [size, mode, fps, useImg]);

  return (
    <div className={className} style={{ width: size, height: size }}>
      {useImg ? (
        <img ref={(e) => { srcRef.current = e; }} src={still} alt="" className="hidden" crossOrigin="anonymous" />
      ) : (
        <video ref={(e) => { srcRef.current = e; }} src={src} autoPlay loop muted playsInline className="hidden"
          onError={() => setUseImg(true)} />
      )}
      <canvas ref={canvas} style={{ width: size, height: size, imageRendering: mode === "pixel" ? "pixelated" : "auto" }} />
    </div>
  );
}
