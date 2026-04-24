export function FAQ({ items, title = "Frequently Asked Questions" }: {
  items: { q: string; a: string }[];
  title?: string;
}) {
  return (
    <section>
      <h2 className="text-2xl font-bold mb-6">{title}</h2>
      <div className="space-y-4">
        {items.map((it) => (
          <details key={it.q} className="card">
            <summary className="cursor-pointer font-semibold">{it.q}</summary>
            <p className="mt-2 text-[var(--text-muted)] text-sm">{it.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
