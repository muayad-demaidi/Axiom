/**
 * AXIOM brand mark — a geometric "A" (apex + two legs + crossbar) that
 * doubles as an upward growth chevron, set in an indigo-gradient rounded
 * square. Inline SVG, so it stays razor-sharp at every size (28px header
 * to large hero) and themes cleanly — unlike the old raster node-graph
 * blob it replaces. Decorative; pair with a visible "AXIOM" wordmark.
 */
export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          id="axiom-mark-grad"
          x1="0"
          y1="0"
          x2="32"
          y2="32"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#6366F1" />
          <stop offset="1" stopColor="#4338CA" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#axiom-mark-grad)" />
      <path d="M16 8 L24 24" stroke="white" strokeWidth="2.8" strokeLinecap="round" />
      <path d="M16 8 L8 24" stroke="white" strokeWidth="2.8" strokeLinecap="round" />
      <path d="M11.4 18.8 H20.6" stroke="white" strokeWidth="2.8" strokeLinecap="round" />
    </svg>
  );
}
