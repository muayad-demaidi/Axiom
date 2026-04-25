"use client";
/**
 * Client wrapper that mounts the ModeProvider once per app shell and
 * renders the global ModeToggle into the header.
 *
 * Kept as a thin client component so the surrounding layout can remain
 * a server component (cheap, no hydration cost on logo / static text).
 *
 * The HeaderToggle is route-aware: inside a project workspace
 * (/app/project/:id and the tool screens reached from it) it controls
 * the *project* mode, so the visible primary toggle always reflects
 * what the chat & tool views are using. Outside a project scope it
 * controls the user-level default.
 */
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ModeProvider } from "@/lib/modeContext";
import { getActiveProjectId } from "@/lib/projectContext";
import { ModeToggle } from "./ModeToggle";

function HeaderToggle() {
  const pathname = usePathname() || "";
  // Match `/app/project/<id>` (the canonical workspace route).
  const projectMatch = pathname.match(/^\/app\/project\/(\d+)/);
  // Tool screens (clean / transform / visualize / predict / statistics
  // / model / upload) inherit the "active project id" from the
  // localStorage breadcrumb so the global toggle keeps editing the
  // right project even when the URL itself is project-agnostic.
  const isToolRoute = /^\/app\/(clean|transform|visualize|predict|statistics|model|upload)(\/|$)/.test(
    pathname
  );

  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  useEffect(() => {
    if (projectMatch) {
      setActiveProjectId(Number(projectMatch[1]));
    } else if (isToolRoute) {
      setActiveProjectId(getActiveProjectId());
    } else {
      setActiveProjectId(null);
    }
  }, [pathname, projectMatch, isToolRoute]);

  const projectScoped = activeProjectId != null;
  return (
    <ModeToggle
      projectId={activeProjectId}
      label={projectScoped ? "PROJECT MODE" : null}
      size="md"
    />
  );
}

export function AppChrome({ children }: { children: React.ReactNode }) {
  return (
    <ModeProvider>
      {children}
    </ModeProvider>
  );
}

/** Re-exported so the layout can render it inline next to the user menu. */
export { HeaderToggle };
