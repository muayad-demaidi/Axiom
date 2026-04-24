"use client";
import { useEffect, useRef } from "react";

/**
 * Decorative animated background: dense Matrix-style streams of monospace
 * glyphs flowing downward, evoking live data ingestion. Renders to a
 * <canvas> and adapts to the active theme via CSS variables
 * --stream-strong / --stream-soft / --stream-fade. Hidden when
 * prefers-reduced-motion.
 */
export function DataStreamBackground({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const fontSize = 14;
    // Mix of digits, latin, brackets, currency, math, and a few cyrillic-ish
    // glyphs so the texture reads as "data" rather than only numbers.
    const glyphs =
      "01010110ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz" +
      "{}[]()<>/\\|=+-*&^%$#@!?:;.,~`БДЖЛПФЦЧШЯабвгдежзилнпфцч";

    type Drop = { y: number; speed: number; trail: number };
    let drops: Drop[] = [];
    let columnCount = 0;
    let width = 0;
    let height = 0;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = Math.floor(rect.width);
      height = Math.floor(rect.height);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = `${fontSize}px "JetBrains Mono", ui-monospace, monospace`;
      ctx.textBaseline = "top";
      columnCount = Math.ceil(width / fontSize);
      // Spread drops across the full section height so the very first
      // paint is already dense — no "warming up" gap visible to users.
      drops = new Array(columnCount).fill(0).map(() => ({
        y: Math.random() * height,
        speed: 0.22 + Math.random() * 0.4,
        trail: 22 + Math.floor(Math.random() * 38),
      }));
    }

    function readVar(name: string, fallback: string) {
      const v = getComputedStyle(document.documentElement)
        .getPropertyValue(name)
        .trim();
      return v || fallback;
    }

    let last = 0;
    function frame(now: number) {
      // ~14fps — calm, ambient feel
      if (now - last < 70) {
        rafRef.current = requestAnimationFrame(frame);
        return;
      }
      last = now;

      const fade = readVar("--stream-fade", "rgba(5,11,31,0.10)");
      const strong = readVar("--stream-strong", "rgba(147,197,253,0.95)");
      const soft = readVar("--stream-soft", "rgba(96,165,250,0.55)");

      // Soft background wash so older glyphs decay into a long tail.
      ctx.fillStyle = fade;
      ctx.fillRect(0, 0, width, height);

      for (let i = 0; i < columnCount; i++) {
        const d = drops[i];
        const x = i * fontSize;

        // Long trail of soft glyphs above the head
        for (let t = 1; t <= d.trail; t++) {
          const ty = d.y - t * fontSize;
          if (ty < -fontSize || ty > height) continue;
          const ch = glyphs[(Math.random() * glyphs.length) | 0];
          // Fade further-up glyphs more aggressively
          const alpha = Math.max(0, 1 - t / d.trail);
          ctx.globalAlpha = alpha * 0.55;
          ctx.fillStyle = soft;
          ctx.fillText(ch, x, ty);
        }

        // Bright "head" glyph
        ctx.globalAlpha = 1;
        ctx.fillStyle = strong;
        const head = glyphs[(Math.random() * glyphs.length) | 0];
        ctx.fillText(head, x, d.y);

        // Advance
        d.y += fontSize * d.speed;

        // Reset when fully off-screen, with a fresh randomized profile
        if (d.y - d.trail * fontSize > height) {
          d.y = -Math.random() * height * 0.5 - fontSize;
          d.speed = 0.22 + Math.random() * 0.4;
          d.trail = 22 + Math.floor(Math.random() * 38);
        }
      }

      ctx.globalAlpha = 1;
      rafRef.current = requestAnimationFrame(frame);
    }

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
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`data-stream pointer-events-none absolute inset-0 h-full w-full ${className}`}
    />
  );
}
