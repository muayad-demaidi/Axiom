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
    <div
      className="text-sm text-[var(--text-muted)] inline-flex items-center gap-2"
      role="status"
      aria-live="polite"
      dir="rtl"
    >
      <span
        className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]"
        aria-hidden="true"
      />
      جاري فتح محادثة المشروع…
    </div>
  );
}
