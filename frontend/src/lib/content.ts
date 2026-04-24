import fs from "node:fs/promises";
import path from "node:path";
import matter from "gray-matter";
import { remark } from "remark";
import remarkGfm from "remark-gfm";
import remarkHtml from "remark-html";
import { z } from "zod";

const sourceSchema = z.object({ label: z.string(), url: z.string().url() });
const statSchema = z.object({
  value: z.string(),
  label: z.string(),
  source: sourceSchema,
});
const faqSchema = z.object({ q: z.string(), a: z.string() });

export const glossarySchema = z.object({
  term: z.string(),
  question: z.string(),
  shortDef: z.string(),
  description: z.string(),
  answer: z.string(),
  stats: z.array(statSchema).default([]),
  faq: z.array(faqSchema).default([]),
  related: z.array(z.string()).default([]),
  relatedGuides: z.array(z.string()).default([]),
  relatedCompare: z.array(z.string()).default([]),
  updated: z.string(),
  jsonLd: z.array(z.record(z.unknown())).optional(),
});

const compareRow = z.object({
  feature: z.string(),
  us: z.string(),
  them: z.string(),
});
export const compareSchema = z.object({
  competitor: z.string(),
  title: z.string(),
  description: z.string(),
  intro: z.string(),
  bestFor: z.object({ us: z.string(), them: z.string() }),
  rows: z.array(compareRow).default([]),
  whenToChoose: z.object({
    us: z.array(z.string()).default([]),
    them: z.array(z.string()).default([]),
  }),
  faq: z.array(faqSchema).default([]),
  relatedGlossary: z.array(z.string()).default([]),
  relatedGuides: z.array(z.string()).default([]),
  updated: z.string(),
});

export const guidesSchema = z.object({
  title: z.string(),
  description: z.string(),
  intro: z.string(),
  estTime: z.string(),
  difficulty: z.enum(["Beginner", "Intermediate", "Advanced"]),
  prerequisites: z.array(z.string()).default([]),
  pitfalls: z.array(z.string()).default([]),
  faq: z.array(faqSchema).default([]),
  relatedGlossary: z.array(z.string()).default([]),
  relatedCompare: z.array(z.string()).default([]),
  updated: z.string(),
  jsonLd: z.array(z.record(z.unknown())).optional(),
});

export type GlossaryEntry = z.infer<typeof glossarySchema>;
export type CompareEntry = z.infer<typeof compareSchema>;
export type GuideEntry = z.infer<typeof guidesSchema>;

const CONTENT_ROOT = path.join(process.cwd(), "content");

async function listSlugs(folder: string): Promise<string[]> {
  try {
    const entries = await fs.readdir(path.join(CONTENT_ROOT, folder));
    return entries
      .filter((f) => f.endsWith(".md"))
      .map((f) => f.replace(/\.md$/, ""))
      .sort();
  } catch {
    return [];
  }
}

async function readEntry<S extends z.ZodTypeAny>(
  folder: string,
  slug: string,
  schema: S,
): Promise<{ slug: string; data: z.infer<S>; body: string; html: string } | null> {
  const file = path.join(CONTENT_ROOT, folder, `${slug}.md`);
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf8");
  } catch {
    return null;
  }
  const parsed = matter(raw);
  const data = schema.parse(parsed.data) as z.infer<S>;
  const html = String(
    await remark().use(remarkGfm).use(remarkHtml).process(parsed.content)
  );
  return { slug, data, body: parsed.content, html };
}

export async function listGlossarySlugs() {
  return listSlugs("glossary");
}
export async function getGlossaryEntry(slug: string) {
  return readEntry("glossary", slug, glossarySchema);
}
export async function getAllGlossary() {
  const slugs = await listGlossarySlugs();
  const out: { slug: string; data: GlossaryEntry; html: string }[] = [];
  for (const s of slugs) {
    const e = await getGlossaryEntry(s);
    if (e) out.push({ slug: e.slug, data: e.data, html: e.html });
  }
  return out;
}

export async function listGuideSlugs() {
  return listSlugs("guides");
}
export async function getGuideEntry(slug: string) {
  return readEntry("guides", slug, guidesSchema);
}
export async function getAllGuides() {
  const slugs = await listGuideSlugs();
  const out: { slug: string; data: GuideEntry; html: string }[] = [];
  for (const s of slugs) {
    const e = await getGuideEntry(s);
    if (e) out.push({ slug: e.slug, data: e.data, html: e.html });
  }
  return out;
}

export async function listCompareSlugs() {
  return listSlugs("compare");
}
export async function getCompareEntry(slug: string) {
  return readEntry("compare", slug, compareSchema);
}
export async function getAllCompare() {
  const slugs = await listCompareSlugs();
  const out: { slug: string; data: CompareEntry; html: string }[] = [];
  for (const s of slugs) {
    const e = await getCompareEntry(s);
    if (e) out.push({ slug: e.slug, data: e.data, html: e.html });
  }
  return out;
}
