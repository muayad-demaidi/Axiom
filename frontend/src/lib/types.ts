export type AxiomUser = {
  id: number;
  email: string;
  username: string;
  subscription_type: string | null;
  trial_end: string | null;
  assistant_mode: string | null;
  is_admin?: boolean;
};

export type AxiomProject = {
  id: number;
  name: string;
  description: string | null;
  mode?: string | null;
  sheet_count?: number;
  total_rows?: number;
  total_size_bytes?: number;
  chat_count?: number;
  last_active_at?: string | null;
  last_session_id?: number | null;
  status?: "ready" | "processing" | "error";
  is_archived?: boolean;
  archived_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DatasetSummaryColumn = { name: string; dtype: string };
export type DatasetSummary = {
  rows: number;
  cols: number;
  columns: DatasetSummaryColumn[];
  report?: Record<string, unknown>;
};

export type JoinProvenance = {
  left_dataset_id: number;
  right_dataset_id: number;
  left_dataset_name?: string | null;
  right_dataset_name?: string | null;
  left_key: string;
  right_key: string;
  join_type: string;
  created_at?: string;
};

export type AxiomDataset = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  project_id?: number | null;
  summary?: DatasetSummary;
  /** Present when the dataset was created by the Join page / chat tool.
   * Used to render the "Joined from X ⋈ Y on KEY" badge and the
   * one-click Undo affordance. */
  join_provenance?: JoinProvenance | null;
};

export type AuthResponse = { token: string; user: AxiomUser };

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// BI types — field metadata, pivot, dashboard. Mirror the shapes the
// FastAPI backend returns from /api/bi/* so the pivot, dashboard and
// field-settings pages stay in lock-step with the central aggregation
// engine.
// ---------------------------------------------------------------------------

export type AxiomAggregation =
  | "sum" | "avg" | "count" | "count_distinct"
  | "min" | "max" | "median" | "none";

export type AxiomRole = "dimension" | "measure" | "key" | "date";
export type AxiomFormatKind = "number" | "integer" | "currency" | "percent" | "date" | "text";

export type AxiomFieldMeta = {
  role: AxiomRole;
  default_agg: AxiomAggregation;
  format_kind: AxiomFormatKind;
  precision: number;
  label: string;
  description?: string;
  visible?: boolean;
  sort_by?: string | null;
  warnings?: string[];
  inferred?: boolean;
  dtype?: string;
  unique?: number;
  cardinality_ratio?: number;
};

export type AxiomFieldMetaResponse = {
  dataset_id: number;
  fields: Record<string, AxiomFieldMeta>;
  overrides: Record<string, Partial<AxiomFieldMeta>>;
  vocab: {
    aggregations: AxiomAggregation[];
    agg_labels: Record<AxiomAggregation, string>;
    roles: AxiomRole[];
    format_kinds: AxiomFormatKind[];
  };
};

export type AxiomMeasureSpec = {
  column?: string;
  aggregation: AxiomAggregation | "ratio";
  label?: string;
  format_kind?: AxiomFormatKind;
  numerator?: string;
  denominator?: string;
  numerator_agg?: AxiomAggregation;
  denominator_agg?: AxiomAggregation;
};

export type AxiomFilter = {
  column: string;
  op: "in" | "not_in" | "between" | "=" | "!=" | ">" | ">=" | "<" | "<="
    | "contains" | "is_null" | "not_null";
  value?: unknown;
  values?: unknown[];
  min?: unknown;
  max?: unknown;
};

export type AxiomPivotMeasureView = {
  key: string;
  label: string;
  aggregation: AxiomAggregation | "ratio";
  column: string | null;
  numerator?: string | null;
  denominator?: string | null;
  format_kind: AxiomFormatKind;
  precision: number;
};

export type AxiomPivotResult = {
  dataset_id?: number;
  rows: Array<{
    _dims: Record<string, unknown>;
    _cols: Record<string, unknown>;
    _subtotal_level?: number;
    [measureKey: string]: unknown;
  }>;
  row_dims: string[];
  col_dims: string[];
  measures: AxiomPivotMeasureView[];
  grand_total: Record<string, number | null>;
  subtotals: Array<Record<string, unknown>>;
  warnings: string[];
  row_count: number;
  result_count: number;
  chart_suggestion?: string;
};

export type AxiomDashboardSlicer = {
  kind: "date_range" | "categorical";
  column: string;
};

export type AxiomDashboardTileSpec = {
  id: string;
  section?: string;
  kind: "kpi" | "bar" | "line" | "table" | "pie" | "stacked_bar";
  title: string;
  rows?: string[];
  cols?: string[];
  measures?: AxiomMeasureSpec[];
  filters?: AxiomFilter[];
  date_grains?: Record<string, string>;
  top_n?: number;
  sort?: Array<{ by: string; dir?: "asc" | "desc" }>;
};

export type AxiomDashboardTileResult = AxiomPivotResult & {
  tile: AxiomDashboardTileSpec;
  error?: string;
  warnings: string[];
};

export type AxiomDashboard = {
  dataset_id: number;
  spec: { tiles: AxiomDashboardTileSpec[]; slicers?: AxiomDashboardSlicer[] };
  tiles: AxiomDashboardTileResult[];
  applied_slicers?: AxiomFilter[];
};

export type AxiomExplainResult = {
  dataset_id: number;
  measure: AxiomPivotMeasureView | Record<string, unknown>;
  value: number | null;
  formula: string;
  filter_summary: string[];
  contributing_rows: number;
  total_rows: number;
  sample_rows: Array<Record<string, unknown>>;
  warnings: string[];
};

export type AxiomModelingSafeguards = {
  dataset_id: number;
  row_count: number;
  grain: { keys: string[]; is_unique: boolean; duplicate_count: number };
  fanout: Array<{ dimension: string; measure: string; ratio: number; warning: string }>;
};

export function errMessage(e: unknown, fallback = "Request failed"): string {
  const isApiError = e instanceof ApiError || (typeof e === "object" && e !== null && "status" in e && "message" in e);
  if (isApiError) {
    const status = (e as ApiError).status;
    const message = (e as ApiError).message;
    if (status === 404) {
      // In bundled production, we can't easily access useTranslations, so we
      // return a string that can be recognized or fallback to the status code.
      return `${fallback} (404: Not Found). Check your deployment configuration and BACKEND_URL.`;
    }
    if (message && message !== "Error" && message !== "undefined" && message !== "Internal Server Error") {
      return message;
    }
    // If it's a generic error but we have a status code, include it.
    return `${fallback} (${status})`;
  }
  if (e instanceof Error) {
    const msg = e.message;
    if (!msg || msg === "Error" || msg === "undefined") return fallback;
    return msg;
  }
  if (typeof e === "string" && e) return e;
  return fallback;
}
