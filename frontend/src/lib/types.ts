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
};

export type DatasetSummaryColumn = { name: string; dtype: string };
export type DatasetSummary = {
  rows: number;
  cols: number;
  columns: DatasetSummaryColumn[];
  report?: Record<string, unknown>;
};

export type AxiomDataset = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  project_id?: number | null;
  summary?: DatasetSummary;
};

export type AuthResponse = { token: string; user: AxiomUser };

export function errMessage(e: unknown, fallback = "Request failed"): string {
  if (e instanceof Error) return e.message || fallback;
  if (typeof e === "string") return e;
  return fallback;
}
