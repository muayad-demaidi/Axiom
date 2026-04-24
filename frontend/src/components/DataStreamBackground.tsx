"use client";
import { useEffect, useRef } from "react";

/**
 * Decorative animated background: streams of monospace glyphs flowing
 * downward, evoking live data ingestion. Renders to a <canvas> and
 * adapts to the active theme via the CSS variables --stream-strong /
 * --stream-soft / --stream-fade. Hidden when prefers-reduced-motion.
 */
export function DataStreamBackground({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const fontSize = 14;
    const glyphs =
      "01234567890123456789ABCDEFabcdef.,;:+-*/=<>{}[]()|#$%&";
    let columns: number[] = [];
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
      columnCount = Math.ceil(width / fontSize);
      columns = new Array(columnCount)
        .fill(0)
        .map(() => Math.random() * height);
    }

    function readVar(name: string, fallback: string) {
      const v = getComputedStyle(document.documentElement)
        .getPropertyValue(name)
        .trim();
      return v || fallback;
    }

    let last = 0;
    function frame(now: number) {
      if (now - last < 70) {
        rafRef.current = requestAnimationFrame(frame);
        return;
      }
      last = now;

      const fade = readVar("--stream-fade", "rgba(5,11,31,0.08)");
      const strong = readVar("--stream-strong", "rgba(96,165,250,0.85)");
      const soft = readVar("--stream-soft", "rgba(96,165,250,0.30)");

      // soft trail wash so glyphs leave a fading tail
      ctx.fillStyle = fade;
      ctx.fillRect(0, 0, width, height);

      for (let i = 0; i < columnCount; i++) {
        const ch = glyphs[(Math.random() * glyphs.length) | 0];
        const x = i * fontSize;
        const y = columns[i];
        ctx.fillStyle = Math.random() < 0.08 ? strong : soft;
        ctx.fillText(ch, x, y);
        if (y > height + Math.random() * 200) {
          columns[i] = -fontSize * Math.random() * 12;
        } else {
          columns[i] = y + fontSize;
        }
      }
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
