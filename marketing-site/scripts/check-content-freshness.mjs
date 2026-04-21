#!/usr/bin/env node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const CONTENT_DIR = join(ROOT, "src", "content");
const COLLECTIONS = ["compare", "glossary", "guides"];

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, "").split("=");
    return [k, v ?? "true"];
  }),
);
const months = Number(args.months ?? 6);
const today = new Date();
const cutoff = new Date(today);
cutoff.setMonth(cutoff.getMonth() - months);

const UPDATED_RE = /^updated:\s*['"]?(\d{4}-\d{2}-\d{2})['"]?\s*$/m;
const VERIFY_RE = /\[verify[^\]]*\]/g;

let stale = [];
let verifyHits = [];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const s = statSync(p);
    if (s.isDirectory()) out.push(...walk(p));
    else if (name.endsWith(".md") || name.endsWith(".ts")) out.push(p);
  }
  return out;
}

for (const collection of COLLECTIONS) {
  const dir = join(CONTENT_DIR, collection);
  let files;
  try {
    files = walk(dir);
  } catch {
    continue;
  }
  for (const file of files) {
    const src = readFileSync(file, "utf8");
    const rel = relative(ROOT, file);
    const m = src.match(UPDATED_RE);
    if (m) {
      const d = new Date(m[1]);
      if (d < cutoff) stale.push({ file: rel, updated: m[1] });
    }
    for (const v of src.matchAll(VERIFY_RE)) {
      verifyHits.push({ file: rel, marker: v[0] });
    }
  }
}

const fmt = (rows) =>
  rows.map((r) => `  - ${r.file}${r.updated ? `  (updated ${r.updated})` : ""}${r.marker ? `  ${r.marker}` : ""}`).join("\n");

console.log(`Content freshness check — threshold: ${months} months (cutoff ${cutoff.toISOString().slice(0, 10)})\n`);

if (stale.length === 0) {
  console.log(`OK — no entries older than ${months} months.`);
} else {
  console.log(`STALE (${stale.length}):`);
  console.log(fmt(stale));
}

if (verifyHits.length > 0) {
  console.log(`\nUNRESOLVED [verify] MARKERS (${verifyHits.length}):`);
  console.log(fmt(verifyHits));
}

const failed = stale.length > 0 || verifyHits.length > 0;
process.exit(failed ? 1 : 0);
