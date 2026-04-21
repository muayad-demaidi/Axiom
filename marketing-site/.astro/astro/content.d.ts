declare module 'astro:content' {
	interface RenderResult {
		Content: import('astro/runtime/server/index.js').AstroComponentFactory;
		headings: import('astro').MarkdownHeading[];
		remarkPluginFrontmatter: Record<string, any>;
	}
	interface Render {
		'.md': Promise<RenderResult>;
	}

	export interface RenderedContent {
		html: string;
		metadata?: {
			imagePaths: Array<string>;
			[key: string]: unknown;
		};
	}
}

declare module 'astro:content' {
	type Flatten<T> = T extends { [K: string]: infer U } ? U : never;

	export type CollectionKey = keyof AnyEntryMap;
	export type CollectionEntry<C extends CollectionKey> = Flatten<AnyEntryMap[C]>;

	export type ContentCollectionKey = keyof ContentEntryMap;
	export type DataCollectionKey = keyof DataEntryMap;

	type AllValuesOf<T> = T extends any ? T[keyof T] : never;
	type ValidContentEntrySlug<C extends keyof ContentEntryMap> = AllValuesOf<
		ContentEntryMap[C]
	>['slug'];

	/** @deprecated Use `getEntry` instead. */
	export function getEntryBySlug<
		C extends keyof ContentEntryMap,
		E extends ValidContentEntrySlug<C> | (string & {}),
	>(
		collection: C,
		// Note that this has to accept a regular string too, for SSR
		entrySlug: E,
	): E extends ValidContentEntrySlug<C>
		? Promise<CollectionEntry<C>>
		: Promise<CollectionEntry<C> | undefined>;

	/** @deprecated Use `getEntry` instead. */
	export function getDataEntryById<C extends keyof DataEntryMap, E extends keyof DataEntryMap[C]>(
		collection: C,
		entryId: E,
	): Promise<CollectionEntry<C>>;

	export function getCollection<C extends keyof AnyEntryMap, E extends CollectionEntry<C>>(
		collection: C,
		filter?: (entry: CollectionEntry<C>) => entry is E,
	): Promise<E[]>;
	export function getCollection<C extends keyof AnyEntryMap>(
		collection: C,
		filter?: (entry: CollectionEntry<C>) => unknown,
	): Promise<CollectionEntry<C>[]>;

	export function getEntry<
		C extends keyof ContentEntryMap,
		E extends ValidContentEntrySlug<C> | (string & {}),
	>(entry: {
		collection: C;
		slug: E;
	}): E extends ValidContentEntrySlug<C>
		? Promise<CollectionEntry<C>>
		: Promise<CollectionEntry<C> | undefined>;
	export function getEntry<
		C extends keyof DataEntryMap,
		E extends keyof DataEntryMap[C] | (string & {}),
	>(entry: {
		collection: C;
		id: E;
	}): E extends keyof DataEntryMap[C]
		? Promise<DataEntryMap[C][E]>
		: Promise<CollectionEntry<C> | undefined>;
	export function getEntry<
		C extends keyof ContentEntryMap,
		E extends ValidContentEntrySlug<C> | (string & {}),
	>(
		collection: C,
		slug: E,
	): E extends ValidContentEntrySlug<C>
		? Promise<CollectionEntry<C>>
		: Promise<CollectionEntry<C> | undefined>;
	export function getEntry<
		C extends keyof DataEntryMap,
		E extends keyof DataEntryMap[C] | (string & {}),
	>(
		collection: C,
		id: E,
	): E extends keyof DataEntryMap[C]
		? Promise<DataEntryMap[C][E]>
		: Promise<CollectionEntry<C> | undefined>;

	/** Resolve an array of entry references from the same collection */
	export function getEntries<C extends keyof ContentEntryMap>(
		entries: {
			collection: C;
			slug: ValidContentEntrySlug<C>;
		}[],
	): Promise<CollectionEntry<C>[]>;
	export function getEntries<C extends keyof DataEntryMap>(
		entries: {
			collection: C;
			id: keyof DataEntryMap[C];
		}[],
	): Promise<CollectionEntry<C>[]>;

	export function render<C extends keyof AnyEntryMap>(
		entry: AnyEntryMap[C][string],
	): Promise<RenderResult>;

	export function reference<C extends keyof AnyEntryMap>(
		collection: C,
	): import('astro/zod').ZodEffects<
		import('astro/zod').ZodString,
		C extends keyof ContentEntryMap
			? {
					collection: C;
					slug: ValidContentEntrySlug<C>;
				}
			: {
					collection: C;
					id: keyof DataEntryMap[C];
				}
	>;
	// Allow generic `string` to avoid excessive type errors in the config
	// if `dev` is not running to update as you edit.
	// Invalid collection names will be caught at build time.
	export function reference<C extends string>(
		collection: C,
	): import('astro/zod').ZodEffects<import('astro/zod').ZodString, never>;

	type ReturnTypeOrOriginal<T> = T extends (...args: any[]) => infer R ? R : T;
	type InferEntrySchema<C extends keyof AnyEntryMap> = import('astro/zod').infer<
		ReturnTypeOrOriginal<Required<ContentConfig['collections'][C]>['schema']>
	>;

	type ContentEntryMap = {
		"compare": {
"datavision-pro-vs-excel.md": {
	id: "datavision-pro-vs-excel.md";
  slug: "datavision-pro-vs-excel";
  body: string;
  collection: "compare";
  data: InferEntrySchema<"compare">
} & { render(): Render[".md"] };
"datavision-pro-vs-looker-studio.md": {
	id: "datavision-pro-vs-looker-studio.md";
  slug: "datavision-pro-vs-looker-studio";
  body: string;
  collection: "compare";
  data: InferEntrySchema<"compare">
} & { render(): Render[".md"] };
"datavision-pro-vs-metabase.md": {
	id: "datavision-pro-vs-metabase.md";
  slug: "datavision-pro-vs-metabase";
  body: string;
  collection: "compare";
  data: InferEntrySchema<"compare">
} & { render(): Render[".md"] };
"datavision-pro-vs-power-bi.md": {
	id: "datavision-pro-vs-power-bi.md";
  slug: "datavision-pro-vs-power-bi";
  body: string;
  collection: "compare";
  data: InferEntrySchema<"compare">
} & { render(): Render[".md"] };
"datavision-pro-vs-tableau.md": {
	id: "datavision-pro-vs-tableau.md";
  slug: "datavision-pro-vs-tableau";
  body: string;
  collection: "compare";
  data: InferEntrySchema<"compare">
} & { render(): Render[".md"] };
};
"glossary": {
"ab-testing.md": {
	id: "ab-testing.md";
  slug: "ab-testing";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"anomaly-detection.md": {
	id: "anomaly-detection.md";
  slug: "anomaly-detection";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"data-cleaning.md": {
	id: "data-cleaning.md";
  slug: "data-cleaning";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"data-drift.md": {
	id: "data-drift.md";
  slug: "data-drift";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"descriptive-statistics.md": {
	id: "descriptive-statistics.md";
  slug: "descriptive-statistics";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"etl-vs-elt.md": {
	id: "etl-vs-elt.md";
  slug: "etl-vs-elt";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"k-means-clustering.md": {
	id: "k-means-clustering.md";
  slug: "k-means-clustering";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"missing-value-imputation.md": {
	id: "missing-value-imputation.md";
  slug: "missing-value-imputation";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"normalization.md": {
	id: "normalization.md";
  slug: "normalization";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"outlier-detection.md": {
	id: "outlier-detection.md";
  slug: "outlier-detection";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"predictive-analytics.md": {
	id: "predictive-analytics.md";
  slug: "predictive-analytics";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
"time-series.md": {
	id: "time-series.md";
  slug: "time-series";
  body: string;
  collection: "glossary";
  data: InferEntrySchema<"glossary">
} & { render(): Render[".md"] };
};
"guides": {
"how-to-ab-test-a-pricing-change.md": {
	id: "how-to-ab-test-a-pricing-change.md";
  slug: "how-to-ab-test-a-pricing-change";
  body: string;
  collection: "guides";
  data: InferEntrySchema<"guides">
} & { render(): Render[".md"] };
"how-to-build-a-3-month-sales-forecast.md": {
	id: "how-to-build-a-3-month-sales-forecast.md";
  slug: "how-to-build-a-3-month-sales-forecast";
  body: string;
  collection: "guides";
  data: InferEntrySchema<"guides">
} & { render(): Render[".md"] };
"how-to-clean-a-messy-csv-in-60-seconds.md": {
	id: "how-to-clean-a-messy-csv-in-60-seconds.md";
  slug: "how-to-clean-a-messy-csv-in-60-seconds";
  body: string;
  collection: "guides";
  data: InferEntrySchema<"guides">
} & { render(): Render[".md"] };
"how-to-compare-this-quarter-vs-last-quarter.md": {
	id: "how-to-compare-this-quarter-vs-last-quarter.md";
  slug: "how-to-compare-this-quarter-vs-last-quarter";
  body: string;
  collection: "guides";
  data: InferEntrySchema<"guides">
} & { render(): Render[".md"] };
"how-to-detect-outliers-in-sales-data.md": {
	id: "how-to-detect-outliers-in-sales-data.md";
  slug: "how-to-detect-outliers-in-sales-data";
  body: string;
  collection: "guides";
  data: InferEntrySchema<"guides">
} & { render(): Render[".md"] };
};

	};

	type DataEntryMap = {
		
	};

	type AnyEntryMap = ContentEntryMap & DataEntryMap;

	export type ContentConfig = typeof import("../../src/content/config.js");
}
