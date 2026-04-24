"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getActiveProjectId } from "@/lib/projectContext";

export default function ChatRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    const pid = getActiveProjectId();
    router.replace(pid ? `/app/project/${pid}` : "/app");
  }, [router]);
  return (
    <div className="text-sm text-[var(--text-muted)]">Opening project chat…</div>
  );
}
