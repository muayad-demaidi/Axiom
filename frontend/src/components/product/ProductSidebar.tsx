"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const sections = [
  {
    label: "DATA",
    items: [
      { href: "/app", label: "Projects" },
      { href: "/app/upload", label: "Upload" },
      { href: "/app/clean", label: "Clean" },
      { href: "/app/transform", label: "Transform" },
    ],
  },
  {
    label: "ANALYSIS",
    items: [
      { href: "/app/statistics", label: "Statistics" },
      { href: "/app/visualize", label: "Visualize" },
      { href: "/app/predict", label: "Predict" },
      { href: "/app/model", label: "Model" },
    ],
  },
  {
    label: "INSIGHT",
    items: [
      { href: "/app/chat", label: "AI Chat" },
      { href: "/app/report", label: "Report" },
    ],
  },
];

export function ProductSidebar() {
  const pathname = usePathname();
  return (
    <aside className="border-r border-[var(--border)] bg-[var(--surface-alt)] p-4 text-sm">
      {sections.map((s) => (
        <div key={s.label} className="mb-6">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-2">{s.label}</div>
          <ul className="space-y-1">
            {s.items.map((it) => {
              const active = pathname === it.href;
              return (
                <li key={it.href}>
                  <Link
                    href={it.href}
                    className={`block px-3 py-1.5 rounded ${active ? "bg-[var(--accent)] text-white" : "text-[var(--text)] hover:bg-[var(--surface)]"}`}
                  >
                    {it.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </aside>
  );
}
