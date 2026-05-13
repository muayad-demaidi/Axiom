"use client";
import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

type Connector = {
  key: string;
  nameKey: string;
  categoryKey: string;
  descKey: string;
  detailKey: string;
  status?: "available" | "soon";
};

// Catalogue keys live in messages/{en,ar}.json under `connectorsCatalog.<key>`.
const CONNECTORS: Connector[] = [
  { key: "postgres", nameKey: "name", categoryKey: "categoryDatabase", descKey: "desc", detailKey: "detail", status: "available" },
  { key: "mysql", nameKey: "name", categoryKey: "categoryDatabase", descKey: "desc", detailKey: "detail" },
  { key: "mongodb", nameKey: "name", categoryKey: "categoryDatabase", descKey: "desc", detailKey: "detail" },
  { key: "snowflake", nameKey: "name", categoryKey: "categoryWarehouse", descKey: "desc", detailKey: "detail" },
  { key: "bigquery", nameKey: "name", categoryKey: "categoryWarehouse", descKey: "desc", detailKey: "detail" },
  { key: "databricks", nameKey: "name", categoryKey: "categoryWarehouse", descKey: "desc", detailKey: "detail" },
  { key: "google-sheets", nameKey: "name", categoryKey: "categorySpreadsheet", descKey: "desc", detailKey: "detail" },
  { key: "airtable", nameKey: "name", categoryKey: "categorySpreadsheet", descKey: "desc", detailKey: "detail" },
  { key: "notion", nameKey: "name", categoryKey: "categoryDocs", descKey: "desc", detailKey: "detail" },
  { key: "stripe", nameKey: "name", categoryKey: "categoryBusiness", descKey: "desc", detailKey: "detail" },
  { key: "hubspot", nameKey: "name", categoryKey: "categoryCRM", descKey: "desc", detailKey: "detail" },
  { key: "salesforce", nameKey: "name", categoryKey: "categoryCRM", descKey: "desc", detailKey: "detail" },
  { key: "linear", nameKey: "name", categoryKey: "categoryProduct", descKey: "desc", detailKey: "detail" },
  { key: "github", nameKey: "name", categoryKey: "categoryProduct", descKey: "desc", detailKey: "detail" },
  { key: "slack", nameKey: "name", categoryKey: "categoryCommunications", descKey: "desc", detailKey: "detail" },
  { key: "google-analytics", nameKey: "name", categoryKey: "categoryMarketing", descKey: "desc", detailKey: "detail" },
  { key: "csv-upload", nameKey: "name", categoryKey: "categoryFiles", descKey: "desc", detailKey: "detail", status: "available" },
  { key: "rest-api", nameKey: "name", categoryKey: "categoryAPI", descKey: "desc", detailKey: "detail" },
];

export default function ConnectorsPage() {
  const t = useTranslations("connectors");
  const tCat = useTranslations("connectorsCatalog");
  const locale = useLocale();
  const dir: "rtl" | "ltr" = locale === "ar" ? "rtl" : "ltr";
  const [open, setOpen] = useState<Connector | null>(null);

  const grouped = CONNECTORS.reduce<Record<string, Connector[]>>((acc, c) => {
    (acc[c.categoryKey] ||= []).push(c);
    return acc;
  }, {});

  return (
    <div className="max-w-5xl" dir={dir}>
      <span className="eyebrow">{t("eyebrow")}</span>
      <h1 className="text-2xl md:text-3xl font-bold mt-2">{t("title")}</h1>
      <p className="text-[var(--text-muted)] mt-2 text-sm max-w-2xl">{t("subtitle")}</p>

      {Object.entries(grouped).map(([catKey, items]) => (
        <section key={catKey} className="mt-8">
          <div className="font-mono text-[12px] tracking-widest uppercase text-[var(--text-muted)] mb-3">
            {t(catKey as Parameters<typeof t>[0])}
          </div>
          <ul className="grid gap-3 md:grid-cols-3">
            {items.map((c) => {
              const name = tCat(`${c.key}.name` as Parameters<typeof tCat>[0]);
              const desc = tCat(`${c.key}.desc` as Parameters<typeof tCat>[0]);
              return (
                <li key={c.key}>
                  <button
                    type="button"
                    onClick={() => setOpen(c)}
                    className="card text-start w-full hover:border-[var(--accent)] transition-colors h-full"
                    style={{ minHeight: 88 }}
                    aria-label={`${name} — ${desc}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-semibold">{name}</h3>
                      {c.status === "available" ? (
                        <span className="text-[12px] font-mono text-emerald-500">{t("statusReady")}</span>
                      ) : (
                        <span className="text-[12px] font-mono text-[var(--text-muted)]">{t("statusConnect")}</span>
                      )}
                    </div>
                    <p className="text-[12px] text-[var(--text-muted)] mt-1.5 leading-relaxed">{desc}</p>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {open && <ConnectorModal connector={open} onClose={() => setOpen(null)} dir={dir} />}
    </div>
  );
}

function ConnectorModal({ connector, onClose, dir }: { connector: Connector; onClose: () => void; dir: "rtl" | "ltr" }) {
  const t = useTranslations("connectors");
  const tCat = useTranslations("connectorsCatalog");
  const name = tCat(`${connector.key}.name` as Parameters<typeof tCat>[0]);
  const detail = tCat(`${connector.key}.detail` as Parameters<typeof tCat>[0]);
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={name}
      dir={dir}
    >
      <div
        className="bg-[var(--surface)] border border-[var(--border)] rounded-xl max-w-md w-full p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-mono text-[12px] tracking-widest uppercase text-[var(--text-muted)]">
              {t(connector.categoryKey as Parameters<typeof t>[0])}
            </div>
            <h3 className="text-lg font-semibold mt-0.5">{name}</h3>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text)] text-xl leading-none inline-flex items-center justify-center"
            style={{ minHeight: 44, minWidth: 44 }}
            aria-label={t("modalClose")}
          >
            ×
          </button>
        </div>
        <p className="text-sm text-[var(--text)] mt-3 leading-relaxed">{detail}</p>
        <div className="mt-5 flex justify-start gap-2">
          {connector.key === "csv-upload" || connector.key === "postgres" ? (
            <Link
              href={connector.key === "csv-upload" ? "/app/upload" : "/app"}
              className="btn btn-primary text-[12px] inline-flex items-center"
              style={{ minHeight: 44 }}
            >
              {connector.key === "csv-upload" ? t("openUploadCta") : t("startChatCta")}
            </Link>
          ) : (
            <button onClick={onClose} className="btn btn-ghost text-[12px]" style={{ minHeight: 44 }}>
              {t("okCta")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
