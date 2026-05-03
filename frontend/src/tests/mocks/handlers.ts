import { http, HttpResponse } from "msw";

export const datasetsFixture = [
  {
    id: 1,
    filename: "sales.csv",
    dataset_name: "sales",
    rows: 1200,
    cols: 8,
    project_id: 1,
  },
  {
    id: 2,
    filename: "customers.csv",
    dataset_name: "customers",
    rows: 350,
    cols: 5,
    project_id: 1,
  },
];

export const projectsFixture = [
  {
    id: 1,
    name: "Demo Project",
    description: "Smoke project",
    sheet_count: 2,
    total_rows: 1550,
    chat_count: 1,
    status: "ready",
  },
];

export const dataModelFixture = {
  description: "Sales by customer",
  confirmed: false,
  tables: [
    {
      id: 11,
      dataset_id: 1,
      dataset_name: "sales",
      rows: 1200,
      cols: 8,
      role: "fact",
      grain: { label: "row per order line" },
      pk_columns: ["order_id"],
      fk_columns: ["customer_id"],
      date_columns: ["order_date"],
      measure_columns: ["amount"],
      suspicious: [
        { column: "amount", kind: "outlier", detail: "5 outliers detected" },
      ],
      columns: [
        { name: "order_id", dtype: "int" },
        { name: "customer_id", dtype: "int" },
        { name: "order_date", dtype: "date" },
        { name: "amount", dtype: "float" },
      ],
      confirmed: false,
    },
    {
      id: 12,
      dataset_id: 2,
      dataset_name: "customers",
      rows: 350,
      cols: 5,
      role: "dimension",
      grain: { label: "row per customer" },
      pk_columns: ["customer_id"],
      fk_columns: [],
      date_columns: [],
      measure_columns: [],
      suspicious: [],
      columns: [
        { name: "customer_id", dtype: "int" },
        { name: "name", dtype: "string" },
        { name: "country", dtype: "string" },
      ],
      confirmed: true,
    },
  ],
  relationships: [
    {
      id: 101,
      left_table: "sales",
      left_column: "customer_id",
      right_table: "customers",
      right_column: "customer_id",
      cardinality: "N:1",
      status: "proposed",
      band: "high",
      confidence: 0.92,
      evidence: ["overlap=0.98", "type match"],
      explanation: "Each sale belongs to one customer.",
    },
  ],
  questions: [
    {
      id: 501,
      kind: "join_clarification",
      prompt: "هل العمود customer_id مفتاح أساسي لجدول العملاء؟",
      status: "open",
      options: [
        { value: "yes", label: "نعم" },
        { value: "no", label: "لا" },
      ],
    },
  ],
};

export const artifactsFixture = [
  {
    id: 1,
    session_id: 1,
    project_id: 1,
    dataset_id: 1,
    kind: "profile",
    title: "Sales profile",
    params: {},
    result: {
      rows: 1200,
      cols: 8,
      duplicate_rows: 5,
      columns: [
        { name: "order_id", dtype: "int", non_null: 1200, missing: 0, missing_pct: 0, unique: 1200 },
        { name: "customer_id", dtype: "int", non_null: 1200, missing: 0, missing_pct: 0, unique: 350 },
        { name: "amount", dtype: "float", non_null: 1195, missing: 5, missing_pct: 0.4, unique: 980 },
      ],
    },
    pinned: false,
    created_at: "2026-05-01T10:00:00Z",
  },
  {
    id: 2,
    session_id: 1,
    project_id: 1,
    dataset_id: 1,
    kind: "chart",
    title: "Sales by month",
    params: {},
    result: {
      kind: "line",
      x: ["Jan", "Feb", "Mar"],
      series: [{ name: "amount", data: [100, 220, 180] }],
    },
    pinned: false,
    created_at: "2026-05-01T10:01:00Z",
  },
  {
    id: 3,
    session_id: 1,
    project_id: 1,
    dataset_id: 1,
    kind: "prediction",
    title: "Predict amount",
    params: {},
    result: {
      target: "amount",
      model: "LinearRegression",
      metrics: { r2: 0.82, mae: 12.5, n_train: 800, n_test: 200 },
      intercept: 5,
      feature_importance: [
        { feature: "qty", coefficient: 1.5, importance: 0.7 },
        { feature: "discount", coefficient: -0.3, importance: 0.2 },
      ],
      feature_ranges: {
        qty: { min: 0, max: 100, mean: 25 },
        discount: { min: 0, max: 0.5, mean: 0.1 },
      },
    },
    pinned: false,
    created_at: "2026-05-01T10:02:00Z",
  },
  {
    id: 4,
    session_id: 1,
    project_id: 1,
    dataset_id: 1,
    kind: "cluster",
    title: "Cluster customers",
    params: {},
    result: { k: 3, cluster_sizes: { "0": 100, "1": 150, "2": 100 } },
    pinned: false,
    created_at: "2026-05-01T10:03:00Z",
  },
  {
    id: 5,
    session_id: 1,
    project_id: 1,
    dataset_id: null,
    kind: "data_model",
    title: "Data model",
    params: {},
    result: dataModelFixture,
    pinned: false,
    created_at: "2026-05-01T10:04:00Z",
  },
];

export const handlers = [
  http.get("/api/datasets", () => HttpResponse.json(datasetsFixture)),
  http.get("/api/projects", () => HttpResponse.json(projectsFixture)),
  http.get("/api/projects/1/data-model", () => HttpResponse.json(dataModelFixture)),
  http.patch("/api/projects/1/data-model/tables/:id", async () =>
    HttpResponse.json({ ok: true }),
  ),
  http.patch("/api/projects/1/data-model/relationships/:id", async () =>
    HttpResponse.json({ ok: true }),
  ),
  http.patch("/api/projects/1/data-model/questions/:id", async () =>
    HttpResponse.json({ ok: true }),
  ),
  http.post("/api/projects/1/data-model/refresh", async () =>
    HttpResponse.json({ ok: true }),
  ),
  http.get("/api/chats/1/artifacts", () => HttpResponse.json(artifactsFixture)),
  http.post("/api/datasets/upload", async () =>
    HttpResponse.json({
      id: 99,
      filename: "uploaded.csv",
      dataset_name: "uploaded",
      rows: 10,
      cols: 3,
      project_id: 1,
    }),
  ),
  http.post("/api/chats", async () =>
    HttpResponse.json({ id: 42, project_id: 1, title: "New chat" }),
  ),
  // i18n user/locale handlers (Task #273 contract).
  http.get("/api/auth/me", () =>
    HttpResponse.json({ id: 1, email: "demo@axiom.app", locale: "en" }),
  ),
  http.get("/api/users/me", () =>
    HttpResponse.json({ id: 1, email: "demo@axiom.app", locale: "en" }),
  ),
  http.patch("/api/users/me/locale", async ({ request }) => {
    const body = (await request.json()) as { locale?: string };
    return HttpResponse.json({
      id: 1,
      email: "demo@axiom.app",
      locale: body?.locale ?? "en",
    });
  }),
  // Login response echoes the Accept-Language header into the
  // returned `locale` so hydration paths that read it post-login can
  // be exercised under both `en` and `ar`.
  http.post("/api/auth/login", async ({ request }) => {
    const accept = request.headers.get("accept-language") || "en";
    const locale = /^ar(\b|-)/i.test(accept) ? "ar" : "en";
    return HttpResponse.json({
      access_token: "test-token",
      token_type: "bearer",
      user: { id: 1, email: "demo@axiom.app", locale },
    });
  }),
];
