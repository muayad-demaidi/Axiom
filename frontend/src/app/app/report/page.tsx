export default function ReportPage() {
  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Insight · Report</span>
      <h1 className="text-2xl font-bold mt-2">Auto-generated reports</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Executive summary with key findings, recommendations, and methodological caveats.
        Wired through <code>/api/report/pdf</code>.
      </p>
      <div className="card mt-6 text-sm text-[var(--text-muted)]">Generate a report from your active project.</div>
    </div>
  );
}
