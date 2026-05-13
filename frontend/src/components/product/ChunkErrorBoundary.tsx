"use client";

import { Component, type ReactNode } from "react";

// Inline fallback wrapper for lazy-loaded artifact renderers
// (ChartRenderer, PredictionCard). When the underlying dynamic import
// or a runtime error inside the rendered component throws, we catch it
// here so the rest of the cleaning / chat output keeps rendering
// instead of bubbling up to the Next.js red runtime overlay.
//
// Stale-chunk auto-recovery (one-time silent reload after a redeploy)
// lives in the global window-level handler installed from
// `app/[locale]/layout.tsx`, so this boundary stays focused on the
// graceful inline fallback.
type Props = {
  children: ReactNode;
  fallback?: ReactNode;
};

type State = { hasError: boolean };

export class ChunkErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div
            role="alert"
            className="text-[12px] text-[var(--text-muted)] p-3 border border-dashed border-[var(--border)] rounded text-center"
          >
            Couldn&apos;t load chart preview — refresh to try again.
          </div>
        )
      );
    }
    return this.props.children;
  }
}
