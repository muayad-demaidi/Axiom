/**
 * AXIOM brand mark — a four-point "AI spark" (a large sparkle plus a
 * small twinkle) in a vivid indigo→violet→pink gradient, the visual
 * language of the current generation of AI tools (Gemini, Notion AI,
 * the ✨ generative motif). Inline SVG, so it stays razor-sharp at every
 * size and renders the gradient cleanly on light or dark. Decorative;
 * pair with a visible "AXIOM" wordmark.
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
          id="axiom-spark-grad"
          x1="3"
          y1="4"
          x2="29"
          y2="29"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#6366F1" />
          <stop offset="0.5" stopColor="#8B5CF6" />
          <stop offset="1" stopColor="#EC4899" />
        </linearGradient>
      </defs>
      {/* main spark */}
      <path
        d="M15 4 Q15 17 28 17 Q15 17 15 30 Q15 17 2 17 Q15 17 15 4 Z"
        fill="url(#axiom-spark-grad)"
      />
      {/* twinkle */}
      <path
        d="M25.5 2.5 Q25.5 7 30 7 Q25.5 7 25.5 11.5 Q25.5 7 21 7 Q25.5 7 25.5 2.5 Z"
        fill="url(#axiom-spark-grad)"
        opacity="0.9"
      />
    </svg>
  );
}
