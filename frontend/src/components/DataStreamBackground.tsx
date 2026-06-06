"use client";
import { useEffect, useRef } from "react";

/**
 * Ambient section background: calm drifting accent glows + a faint grid,
 * with a refined "data stream" of falling glyphs layered on top.
 *
 * The stream is deliberately understated — sparse, dim, slow, in the
 * brand indigo, and radially masked so it fades to nothing in the centre
 * (behind the headline) and only whispers at the edges. It keeps the
 * "live data ingestion" motif without the old Matrix-rain wall fighting
 * the copy. Fully stilled under prefers-reduced-motion.
 */
export function DataStreamBackground({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const fontSize = 16;
    // Wider column spacing than 1 glyph → a sparse, airy stream.
    const colStep = fontSize * 1.9;
    const glyphs =
      "0101ABEFHKLMNPRTXZ{}[]()<>/\\|=+-*·%$#@?:;.~БДЖЛПФЦ";

    type Drop = { y: number; speed: number; trail: number };
    let drops: Drop[] = [];
    let columnCount = 0;
    let width = 0;
    let height = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = Math.floor(rect.width);
      height = Math.floor(rect.height);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = `500 ${fontSize}px "JetBrains Mono", ui-monospace, monospace`;
      ctx.textBaseline = "top";
      columnCount = Math.ceil(width / colStep);
      drops = new Array(columnCount).fill(0).map(() => ({
        y: Math.random() * height,
        speed: 0.12 + Math.random() * 0.22,
        trail: 8 + Math.floor(Math.random() * 16),
      }));
    };

    const readVar = (name: string, fallback: string) =>
      getComputedStyle(document.documentElement).getPropertyValue(name).trim() ||
      fallback;

    let last = 0;
    const frame = (now: number) => {
      // ~12fps — slow, ambient.
      if (now - last < 84) {
        rafRef.current = requestAnimationFrame(frame);
        return;
      }
      last = now;

      const fade = readVar("--stream-fade", "rgba(5,11,31,0.10)");
      const strong = readVar("--stream-strong", "rgba(129,140,248,0.65)");
      const soft = readVar("--stream-soft", "rgba(99,102,241,0.28)");

      ctx.fillStyle = fade;
      ctx.fillRect(0, 0, width, height);

      for (let i = 0; i < columnCount; i++) {
        const d = drops[i];
        const x = Math.round(i * colStep);
        for (let t = 1; t <= d.trail; t++) {
          const ty = Math.round(d.y - t * fontSize);
          if (ty < -fontSize || ty > height) continue;
          const ch = glyphs[(Math.random() * glyphs.length) | 0];
          ctx.globalAlpha = Math.max(0, 1 - t / d.trail) * 0.55;
          ctx.fillStyle = soft;
          ctx.fillText(ch, x, ty);
        }
        ctx.globalAlpha = 0.95;
        ctx.fillStyle = strong;
        ctx.fillText(glyphs[(Math.random() * glyphs.length) | 0], x, Math.round(d.y));

        d.y += fontSize * d.speed;
        if (d.y - d.trail * fontSize > height) {
          d.y = -Math.random() * height * 0.5 - fontSize;
          d.speed = 0.12 + Math.random() * 0.22;
          d.trail = 8 + Math.floor(Math.random() * 16);
        }
      }
      ctx.globalAlpha = 1;
      rafRef.current = requestAnimationFrame(frame);
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    rafRef.current = requestAnimationFrame(frame);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, []);

  return (
    <div
      aria-hidden="true"
      className={`ambient-bg pointer-events-none absolute inset-0 h-full w-full overflow-hidden ${className}`}
    >
      <div className="ambient-grid absolute inset-0" />
      <div className="ambient-glow ambient-glow-1" />
      <div className="ambient-glow ambient-glow-2" />
      <div className="ambient-glow ambient-glow-3" />
      <canvas
        ref={canvasRef}
        className="data-stream-canvas pointer-events-none absolute inset-0 h-full w-full"
      />
    </div>
  );
}
