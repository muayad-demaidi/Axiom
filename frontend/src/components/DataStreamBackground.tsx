/**
 * Ambient section background: a calm field of softly drifting accent
 * "aurora" glows over a faint grid.
 *
 * Replaces the previous Matrix-rain canvas, which fought the copy for
 * attention, hurt legibility, and read as a gimmick rather than the
 * "clean, trustworthy, no-code" promise the product makes. Pure CSS —
 * no <canvas>/requestAnimationFrame, GPU-friendly, and fully calmed
 * under prefers-reduced-motion (handled in globals.css).
 */
export function DataStreamBackground({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`ambient-bg pointer-events-none absolute inset-0 h-full w-full overflow-hidden ${className}`}
    >
      <div className="ambient-grid absolute inset-0" />
      <div className="ambient-glow ambient-glow-1" />
      <div className="ambient-glow ambient-glow-2" />
      <div className="ambient-glow ambient-glow-3" />
    </div>
  );
}
