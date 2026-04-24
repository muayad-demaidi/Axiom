#!/usr/bin/env node
/**
 * ping-search-engines.mjs
 *
 * Submits new and changed URLs from the freshly built marketing-site sitemap to:
 *   1. IndexNow (Bing, Yandex, Seznam, Naver) — always, if INDEXNOW_KEY is set
 *   2. Google Indexing API — only if GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON is set
 *      (note: Google officially supports this API only for JobPosting and
 *      BroadcastEvent pages; general use is opt-in and may be ignored)
 *
 * Reads the sitemap from marketing-site/dist/, diffs against a state file at
 * marketing-site/.indexnow-state.json (URL -> last-pinged lastmod), and only
 * pings URLs that are new or whose lastmod has changed.
 *
 * Safe to run on every deploy:
 *   - No-op when no URLs changed
 *   - No-op (with a warning) when INDEXNOW_KEY is not set
 *   - Failures are logged but do not exit non-zero, so they never break a deploy
 *
 * Usage:
 *   node scripts/ping-search-engines.mjs
 *
 * Env vars:
 *   INDEXNOW_KEY                          IndexNow key (32+ hex chars). Required to ping.
 *   INDEXNOW_KEY_LOCATION                 Optional. Defaults to https://<host>/<key>.txt
 *   GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON  Optional. Raw service-account JSON string.
 *   SITEMAP_PATH                          Optional. Defaults to marketing-site/dist/sitemap.xml
 *                                         (falls back to sitemap-index.xml if present).
 *   STATE_PATH                            Optional. Defaults to marketing-site/.indexnow-state.json
 *   DRY_RUN                               If "1", logs what would be pinged but sends nothing.
 */

import { readFile, writeFile, access } from "node:fs/promises";
import { constants as fsConstants, createSign } from "node:crypto";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

// Unified Next.js app produces a single sitemap at frontend/.next/server/app/sitemap.xml.body
// after `next build`; once exported it is served from `/sitemap.xml`. We also fall back to the
// legacy Astro location if it still exists during the parity window.
const DEFAULT_SITEMAP = resolve(ROOT, "frontend/.next/server/app/sitemap.xml.body");
const DEFAULT_SITEMAP_INDEX = resolve(ROOT, "marketing-site/dist/sitemap-index.xml");
const DEFAULT_STATE = resolve(ROOT, ".indexnow-state.json");

const SITEMAP_PATH = process.env.SITEMAP_PATH
  ? resolve(ROOT, process.env.SITEMAP_PATH)
  : null;
const STATE_PATH = resolve(ROOT, process.env.STATE_PATH || ".local/none");
const STATE_FILE = process.env.STATE_PATH ? STATE_PATH : DEFAULT_STATE;

const DRY_RUN = process.env.DRY_RUN === "1";

function log(...args) {
  console.log("[ping-search-engines]", ...args);
}
function warn(...args) {
  console.warn("[ping-search-engines][warn]", ...args);
}
function err(...args) {
  console.error("[ping-search-engines][error]", ...args);
}

async function fileExists(p) {
  try {
    await access(p, fsConstants.R_OK);
    return true;
  } catch {
    return false;
  }
}

async function resolveSitemap() {
  if (SITEMAP_PATH) return SITEMAP_PATH;
  if (await fileExists(DEFAULT_SITEMAP_INDEX)) return DEFAULT_SITEMAP_INDEX;
  if (await fileExists(DEFAULT_SITEMAP)) return DEFAULT_SITEMAP;
  return null;
}

function parseSitemapXml(xml) {
  const out = [];
  const re = /<url>([\s\S]*?)<\/url>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    const block = m[1];
    const loc = (block.match(/<loc>([^<]+)<\/loc>/) || [])[1];
    const lastmod = (block.match(/<lastmod>([^<]+)<\/lastmod>/) || [])[1] || "";
    if (loc) out.push({ loc: loc.trim(), lastmod: lastmod.trim() });
  }
  return out;
}

async function gatherUrls(initialPath) {
  const xml = await readFile(initialPath, "utf8");
  if (xml.includes("<sitemapindex")) {
    const re = /<sitemap>[\s\S]*?<loc>([^<]+)<\/loc>[\s\S]*?<\/sitemap>/g;
    const childUrls = [];
    let m;
    while ((m = re.exec(xml)) !== null) childUrls.push(m[1].trim());

    // Prefer reading child sitemaps from the freshly built local artifacts
    // (the same `dist/` directory the index lives in). Fetching by absolute
    // URL would point at the currently-LIVE site, which is the previous
    // deploy — not the new build — and would silently miss new/changed URLs.
    const distDir = dirname(initialPath);
    const all = [];
    for (const childUrl of childUrls) {
      let parsed;
      try {
        parsed = new URL(childUrl);
      } catch {
        warn(`Could not parse child sitemap URL ${childUrl}, skipping.`);
        continue;
      }
      const localPath = resolve(
        distDir,
        "." + parsed.pathname.replace(/^\/+/, "/")
      );
      if (await fileExists(localPath)) {
        all.push(...parseSitemapXml(await readFile(localPath, "utf8")));
        continue;
      }
      // Fallback: fetch over HTTP (logged loudly so operators notice).
      warn(
        `Child sitemap not found locally at ${localPath} — falling back to HTTP fetch of ${childUrl}. ` +
          `This may return STALE content from the previous deploy.`
      );
      try {
        const res = await fetch(childUrl);
        if (!res.ok) {
          warn(`Could not fetch child sitemap ${childUrl}: HTTP ${res.status}`);
          continue;
        }
        all.push(...parseSitemapXml(await res.text()));
      } catch (e) {
        warn(`Failed to fetch child sitemap ${childUrl}: ${e.message}`);
      }
    }
    return all;
  }
  return parseSitemapXml(xml);
}

async function loadState() {
  try {
    const raw = await readFile(STATE_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function saveState(state) {
  if (DRY_RUN) return;
  await writeFile(STATE_FILE, JSON.stringify(state, null, 2) + "\n", "utf8");
}

function diffUrls(current, prevState) {
  const changed = [];
  for (const { loc, lastmod } of current) {
    const prev = prevState[loc];
    if (prev !== lastmod) changed.push({ loc, lastmod });
  }
  return changed;
}

async function pingIndexNow(urls) {
  const key = process.env.INDEXNOW_KEY;
  if (!key) {
    warn(
      "INDEXNOW_KEY not set — skipping IndexNow submission. " +
        "URLs will NOT be marked as pinged, so they will be retried on the next deploy."
    );
    return { skipped: true, success: false };
  }
  if (urls.length === 0) return { skipped: false, count: 0, success: true };

  const host = new URL(urls[0].loc).host;
  const keyLocation =
    process.env.INDEXNOW_KEY_LOCATION || `https://${host}/${key}.txt`;

  const body = {
    host,
    key,
    keyLocation,
    urlList: urls.map((u) => u.loc),
  };

  log(
    `IndexNow: ${DRY_RUN ? "would ping" : "pinging"} ${urls.length} URL(s) ` +
      `at host=${host} keyLocation=${keyLocation}`
  );
  for (const u of urls) log(`  - ${u.loc} (lastmod=${u.lastmod || "-"})`);

  if (DRY_RUN) {
    return { skipped: false, count: urls.length, dryRun: true, success: false };
  }

  try {
    const res = await fetch("https://api.indexnow.org/indexnow", {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(body),
    });
    log(`IndexNow response: HTTP ${res.status}`);
    // IndexNow returns 200 or 202 on success.
    const success = res.status === 200 || res.status === 202;
    if (!success) {
      const text = await res.text().catch(() => "");
      warn(
        `IndexNow non-success body: ${text.slice(0, 500)} — URLs will be retried on next deploy.`
      );
    }
    return { skipped: false, count: urls.length, status: res.status, success };
  } catch (e) {
    err(`IndexNow request failed: ${e.message} — URLs will be retried on next deploy.`);
    return { skipped: false, count: urls.length, error: e.message, success: false };
  }
}

function base64url(buf) {
  return Buffer.from(buf)
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

async function googleAccessToken(serviceAccount) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = {
    iss: serviceAccount.client_email,
    scope: "https://www.googleapis.com/auth/indexing",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  };
  const signingInput =
    base64url(JSON.stringify(header)) + "." + base64url(JSON.stringify(claim));
  const signer = createSign("RSA-SHA256");
  signer.update(signingInput);
  const signature = base64url(signer.sign(serviceAccount.private_key));
  const jwt = signingInput + "." + signature;

  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt,
    }),
  });
  if (!res.ok) {
    throw new Error(
      `Google token exchange failed: HTTP ${res.status} ${await res
        .text()
        .catch(() => "")}`
    );
  }
  const data = await res.json();
  return data.access_token;
}

async function pingGoogleIndexing(urls) {
  const raw = process.env.GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON;
  if (!raw) {
    log("GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON not set — skipping Google Indexing API.");
    return { skipped: true };
  }
  if (urls.length === 0) return { skipped: false, count: 0 };

  let serviceAccount;
  try {
    serviceAccount = JSON.parse(raw);
  } catch (e) {
    err(`GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON is not valid JSON: ${e.message}`);
    return { skipped: false, error: "invalid-json" };
  }

  log(`Google Indexing API: would ping ${urls.length} URL(s)`);
  if (DRY_RUN) return { skipped: false, count: urls.length, dryRun: true };

  let token;
  try {
    token = await googleAccessToken(serviceAccount);
  } catch (e) {
    err(e.message);
    return { skipped: false, error: e.message };
  }

  let ok = 0;
  let fail = 0;
  const successUrls = new Set();
  for (const { loc } of urls) {
    try {
      const res = await fetch(
        "https://indexing.googleapis.com/v3/urlNotifications:publish",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ url: loc, type: "URL_UPDATED" }),
        }
      );
      if (res.ok) {
        ok++;
        successUrls.add(loc);
        log(`  Google ✓ ${loc}`);
      } else {
        fail++;
        const body = await res.text().catch(() => "");
        warn(`  Google ✗ ${loc} HTTP ${res.status} ${body.slice(0, 200)}`);
      }
    } catch (e) {
      fail++;
      warn(`  Google ✗ ${loc} ${e.message}`);
    }
  }
  return { skipped: false, count: urls.length, ok, fail, successUrls };
}

async function main() {
  const sitemapPath = await resolveSitemap();
  if (!sitemapPath) {
    warn(
      "No sitemap found at marketing-site/dist/sitemap.xml or sitemap-index.xml. " +
        "Did you run `npm run build` in marketing-site/?"
    );
    return;
  }
  log(`Reading sitemap: ${sitemapPath}`);

  const current = await gatherUrls(sitemapPath);
  log(`Sitemap contains ${current.length} URL(s).`);

  const prev = await loadState();
  const isFirstRun = Object.keys(prev).length === 0;
  const changed = diffUrls(current, prev);

  if (isFirstRun) {
    log(
      `First run (no prior state). Treating all ${changed.length} URL(s) as new.`
    );
  } else {
    log(`${changed.length} URL(s) new or changed since last ping.`);
  }

  if (changed.length === 0) {
    log("Nothing to ping. Done.");
    return;
  }

  const indexNowResult = await pingIndexNow(changed);
  const googleResult = await pingGoogleIndexing(changed);

  // Persist state per-URL: a URL is considered "pinged" (and thus won't be
  // resent next deploy unless its lastmod changes) only if at least one
  // configured provider successfully accepted it. This keeps the diff honest
  // even when only one of the two providers is configured:
  //   - IndexNow is batch (all-or-nothing), so on success every URL in the
  //     batch counts as pinged.
  //   - Google Indexing API is per-URL, so only the URLs it acked count.
  // URLs that no provider accepted are left untouched in state and will be
  // retried on the next deploy.
  let stateWritten = false;
  if (!DRY_RUN) {
    const successUrls = new Set();
    if (indexNowResult.success) {
      for (const { loc } of changed) successUrls.add(loc);
    }
    if (googleResult.successUrls) {
      for (const loc of googleResult.successUrls) successUrls.add(loc);
    }
    if (successUrls.size > 0) {
      const nextState = { ...prev };
      for (const { loc, lastmod } of changed) {
        if (successUrls.has(loc)) nextState[loc] = lastmod;
      }
      await saveState(nextState);
      stateWritten = true;
      log(`Persisted state for ${successUrls.size}/${changed.length} URL(s).`);
    }
  }

  // Strip non-serializable Set before logging.
  const googleLog = { ...googleResult };
  if (googleLog.successUrls) googleLog.successUrls = googleLog.successUrls.size;
  log(
    `Done. IndexNow=${JSON.stringify(indexNowResult)} Google=${JSON.stringify(
      googleLog
    )} state=${
      DRY_RUN
        ? "(dry-run, not written)"
        : stateWritten
        ? STATE_FILE
        : "(not written — pings did not succeed; will retry next deploy)"
    }`
  );
}

main().catch((e) => {
  err(`Unexpected failure: ${e.stack || e.message}`);
  // Never fail a deploy because of a ping issue.
  process.exit(0);
});
