import { defineCollection, z } from "astro:content";

const sourceSchema = z.object({
  label: z.string(),
  url: z.string().url(),
});

const statSchema = z.object({
  value: z.string(),
  label: z.string(),
  source: sourceSchema,
});

const faqSchema = z.object({
  q: z.string(),
  a: z.string(),
});

const glossary = defineCollection({
  type: "content",
  schema: z.object({
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
  }),
});

const compareRow = z.object({
  feature: z.string(),
  us: z.string(),
  them: z.string(),
});

const compare = defineCollection({
  type: "content",
  schema: z.object({
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
  }),
});

const guides = defineCollection({
  type: "content",
  schema: z.object({
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
  }),
});

export const collections = { glossary, compare, guides };
