"use client";
import { useState } from "react";
import Link from "next/link";

type Connector = {
  key: string;
  name: string;
  category: string;
  description: string;
  detail: string;
  status?: "available" | "soon";
};

// Curated list of data-relevant integrations supported on Replit.
// Each card explains what the connector does; the modal walks the user
// through asking the AXIOM agent (in the Replit chat) to wire it up,
// since Replit integrations are provisioned at the workspace level.
const CONNECTORS: Connector[] = [
  {
    key: "postgres",
    name: "PostgreSQL",
    category: "Database",
    description: "Query a managed Postgres database — already wired into AXIOM.",
    detail:
      "AXIOM ships with a Replit-managed Postgres database. You can ask the assistant to read from any of your tables — no extra setup.",
    status: "available",
  },
  {
    key: "mysql",
    name: "MySQL",
    category: "Database",
    description: "Connect to a MySQL or MariaDB instance.",
    detail: "Add a MYSQL_URL secret in Replit and tell the assistant which tables to read.",
  },
  {
    key: "mongodb",
    name: "MongoDB",
    category: "Database",
    description: "Pull collections from MongoDB Atlas or self-hosted.",
    detail: "Add a MONGODB_URI secret. The assistant can flatten documents into tabular views for analysis.",
  },
  {
    key: "snowflake",
    name: "Snowflake",
    category: "Warehouse",
    description: "Run analytics over Snowflake warehouses.",
    detail: "Add SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD secrets to enable.",
  },
  {
    key: "bigquery",
    name: "BigQuery",
    category: "Warehouse",
    description: "Query Google BigQuery datasets directly.",
    detail: "Connect a Google service account via Replit's Google integration to authorize BigQuery reads.",
  },
  {
    key: "databricks",
    name: "Databricks",
    category: "Warehouse",
    description: "Read tables from a Databricks workspace.",
    detail: "Add DATABRICKS_HOST and DATABRICKS_TOKEN secrets to enable SQL warehouse queries.",
  },
  {
    key: "google-sheets",
    name: "Google Sheets",
    category: "Spreadsheet",
    description: "Pull live data from a Google Sheet into a chat.",
    detail: "Use Replit's Google integration to authorise read access, then point the assistant at a sheet URL.",
  },
  {
    key: "airtable",
    name: "Airtable",
    category: "Spreadsheet",
    description: "Sync bases and views as datasets.",
    detail: "Add an AIRTABLE_API_KEY secret and the base ID. Each table becomes a dataset.",
  },
  {
    key: "notion",
    name: "Notion",
    category: "Docs",
    description: "Use a Notion database as a structured source.",
    detail: "Connect Notion via Replit's integration; the assistant can read databases and rich text.",
  },
  {
    key: "stripe",
    name: "Stripe",
    category: "Business",
    description: "Analyze charges, customers, subscriptions.",
    detail: "Connect Stripe via Replit's integration; the assistant can pull payments, customers, and MRR.",
  },
  {
    key: "hubspot",
    name: "HubSpot",
    category: "CRM",
    description: "Pipeline, contacts, and deals analysis.",
    detail: "Connect HubSpot via Replit's integration; the assistant can read contacts, deals, and pipelines.",
  },
  {
    key: "salesforce",
    name: "Salesforce",
    category: "CRM",
    description: "Read accounts, opportunities, and reports.",
    detail: "Connect Salesforce via Replit's integration; the assistant can run SOQL on your behalf.",
  },
  {
    key: "linear",
    name: "Linear",
    category: "Product",
    description: "Issue and cycle analytics.",
    detail: "Connect Linear via Replit's integration; the assistant can pull issues, cycles, and trends.",
  },
  {
    key: "github",
    name: "GitHub",
    category: "Product",
    description: "Repository activity, PRs, and issues.",
    detail: "Connect GitHub via Replit's integration to analyze contribution, PR throughput, and issues.",
  },
  {
    key: "slack",
    name: "Slack",
    category: "Communications",
    description: "Channel activity and message exports.",
    detail: "Connect Slack via Replit's integration to summarise channels and analyse engagement.",
  },
  {
    key: "google-analytics",
    name: "Google Analytics",
    category: "Marketing",
    description: "Site traffic and acquisition data.",
    detail: "Authorise via Replit's Google integration; the assistant can pull GA4 reports.",
  },
  {
    key: "csv-upload",
    name: "CSV / Excel upload",
    category: "Files",
    description: "Drop a CSV or Excel workbook into a project.",
    detail: "Use the Files page to upload — supported anywhere AXIOM runs, no setup required.",
    status: "available",
  },
  {
    key: "rest-api",
    name: "REST / JSON",
    category: "API",
    description: "Pull from any HTTP API into a dataset.",
    detail: "Tell the assistant the endpoint and auth header; it will fetch and tabulate the response.",
  },
];

export default function ConnectorsPage() {
  const [open, setOpen] = useState<Connector | null>(null);

  const grouped = CONNECTORS.reduce<Record<string, Connector[]>>((acc, c) => {
    (acc[c.category] ||= []).push(c);
    return acc;
  }, {});

  return (
    <div className="max-w-5xl">
      <span className="eyebrow">Workspace</span>
      <h1 className="text-2xl md:text-3xl font-bold mt-2">Data connectors</h1>
      <p className="text-[var(--text-muted)] mt-2 text-sm max-w-2xl">
        Bring data into AXIOM from any source. Some sources are already wired
        in; others are provisioned through Replit&apos;s integration system —
        click a card to see how to connect it.
      </p>

      {Object.entries(grouped).map(([cat, items]) => (
        <section key={cat} className="mt-8">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-3">
            {cat}
          </div>
          <ul className="grid gap-3 md:grid-cols-3">
            {items.map((c) => (
              <li key={c.key}>
                <button
                  type="button"
                  onClick={() => setOpen(c)}
                  className="card text-left w-full hover:border-[var(--accent)] transition-colors h-full"
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold">{c.name}</h3>
                    {c.status === "available" ? (
                      <span className="text-[10px] font-mono text-emerald-500">READY</span>
                    ) : (
                      <span className="text-[10px] font-mono text-[var(--text-muted)]">CONNECT</span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--text-muted)] mt-1.5 leading-relaxed">
                    {c.description}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {open && <ConnectorModal connector={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function ConnectorModal({ connector, onClose }: { connector: Connector; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-[var(--surface)] border border-[var(--border)] rounded-xl max-w-md w-full p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)]">
              {connector.category}
            </div>
            <h3 className="text-lg font-semibold mt-0.5">{connector.name}</h3>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text)] text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <p className="text-sm text-[var(--text)] mt-3 leading-relaxed">{connector.detail}</p>
        <div className="mt-5 flex justify-end gap-2">
          {connector.key === "csv-upload" || connector.key === "postgres" ? (
            <Link
              href={connector.key === "csv-upload" ? "/app/upload" : "/app"}
              className="btn btn-primary text-xs"
            >
              {connector.key === "csv-upload" ? "Open uploader" : "Start a chat"}
            </Link>
          ) : (
            <button onClick={onClose} className="btn btn-ghost text-xs">
              Got it
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
