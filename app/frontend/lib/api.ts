"use client";

export type Gazette = {
  id: string;
  filename: string;
  sha256: string;
  gazette_type: "A" | "B";
  issue_year: number | null;
  issue_number: number | null;
  status: "uploaded" | "processing" | "completed" | "failed";
  row_count: number;
  error_message: string | null;
  uploaded_at: string;
  processed_at: string | null;
  size_bytes: number;
  ocr_confidence: number | null;
  flagged_row_count: number | null;
  needs_review: boolean;
};

export type AdminCheck = { isAdmin: boolean; reason: string };

export type Trademark = {
  id: string;
  gazette_id: string;
  record_type: "A" | "B_domestic" | "B_madrid";
  application_number: string | null;
  certificate_number: string | null;
  madrid_number: string | null;
  publication_date_441: string | null;
  publication_date_450: string | null;
  registration_date_151: string | null;
  nice_classes: string[] | null;
  nice_total: number | null;
  mark_sample: string | null;
  /** Path relative to /static/image/ of the extracted logo PNG, or null when
   * no logo was extracted (text-only mark, extraction skipped, or pre-Phase-2
   * row). Frontend prepends "/static/image/" to form the URL. */
  logo_path: string | null;
  applicant_name: string | null;
  applicant_country_code: string | null;
  applicant_city: string | null;
  applicant_type: string | null;
  ip_agency: string | null;
  mark_status: string | null;
  protected_colors: string | null;
  validity_171: string | null;
  validity_176: string | null;
  submission_date: string | null;
  expiry_date_141: string | null;
  expiry_date_181: string | null;
  year: number | null;
  month: number | null;
};

export type TrademarkListResponse = {
  items: Trademark[];
  total: number;
  limit: number;
  offset: number;
};

export type GazetteListResponse = { items: Gazette[]; total: number };

export type SearchParams = {
  q?: string;
  country?: string;
  nice_class?: string[];
  record_type?: string;
  applicant_type?: string;
  year?: number;
  month?: number;
  gazette_id?: string;
  ip_agency?: string;
  limit?: number;
  offset?: number;
};

export type StatsOverview = {
  total: number;
  by_record_type: Record<string, number>;
  gazettes_total: number;
  gazettes_completed: number;
  gazettes_in_flight: number;
};

export type CountBucket = { key: string; label: string | null; count: number };

function qs(p: Record<string, unknown>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.append(k, String(v));
  }
  return u.toString();
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    // FastAPI returns structured errors as `{detail: "..."}`. Surface that to
    // the caller (toast / error UI) instead of swallowing it into a bare status
    // code. .catch handles non-JSON error bodies (e.g. an HTML 502 page).
    const body = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `${url} -> ${r.status}`);
  }
  return r.json();
}

export type TodayDigest = {
  today: string;
  totalNew: number;
  activeWatchlists: number;
  watchlistsWithFindings: number;
  closingIn7Days: number;
  closingIn14Days: number;
  lastSyncAt: string;
};

export type Finding = {
  mark: Trademark;
  score: number;
  watchId: string;
  watchName: string;
  reason: string;
  matchedClasses: string[];
};

export type OppositionWindow = {
  markId: string;
  markName: string | null;
  applicant: string | null;
  classes: string[];
  closesAt: string;
  daysLeft: number;
  status: "open" | "closed";
  watchId: string | null;
  watchName: string | null;
  publishedAt: string | null;
};

export type WatchQuery = {
  q?: string | null;
  mode?: SearchMode;
  threshold?: number;
  country?: string | null;
  nice_class?: string[] | null;
  nice_class_mode?: NiceMode;
  record_type?: string | null;
  applicant_type?: string | null;
  ip_agency?: string | null;
};

export type Watchlist = {
  id: string;
  name: string;
  client: string | null;
  matter: string | null;
  query: WatchQuery;
  queryDesc: string | null;
  totalCount: number;
  newCount: number;
  createdAt: string;
  updatedAt: string;
  lastRunAt: string | null;
};

export type SearchMode = "text" | "phonetic" | "image" | "vienna";
export type SortKey = "similarity" | "publication-desc" | "applicant-asc" | "class-count";
export type NiceMode = "any" | "all";

export type ScoredMark = { mark: Trademark; score: number };

export type SearchResults = {
  items: ScoredMark[];
  total: number;
  limit: number;
  offset: number;
};

export type ScoredSearchParams = SearchParams & {
  mode?: SearchMode;
  threshold?: number;
  nice_class_mode?: NiceMode;
  sort?: SortKey;
};

export type MarkDetail = {
  mark: Trademark;
  oppositionEnds: string | null;
  oppositionDaysLeft: number | null;
  oppositionOpen: boolean;
  statusLabel: string;
  statusTone: "warn" | "ok" | "mute";
  // (511) goods-and-services text from the gazette. "Nhóm N: …" per-class
  // format for VN A-files + B-domestic; bare class list ("05, 12.") for
  // Madrid B. Empty when the row was published without a (511) value.
  raw_511_text: string | null;
};

export type TimelineEvent = {
  kind: "filed" | "formal" | "exam" | "published" | "opposition" | "registration" | "registered" | "renewal";
  date: string;
  label: string;
  body: string;
  done: boolean;
  current?: boolean;
  anchor?: boolean;
};

export type CoMark = {
  id: string;
  name: string;
  year: number | null;
  classes: string[];
};

export type SimilarMark = { mark: Trademark; score: number };

export type ApplicantStats = {
  name: string;
  activeMarks: number;
  pending: number;
  oppositionsFiled: number;
  totalMarks: number;
};

export type InidMarker = { code: string; label: string; value: string | null };

export type PairScore = {
  markId: string;
  phonetic: number;
  visual: number;
  classOverlap: number;
  composite: number;
  verdict: string;       // "Likely conflict" | "Possible conflict" | "Low risk"
  verdictTone: "stamp" | "warn" | "ok";
};

export type CompareResponse = {
  anchorId: string;
  marks: Trademark[];
  scores: PairScore[];
  weights: Record<string, number>;
};

export type PipelineStats = {
  totalTrademarks: number;
  thisQuarter: number;
  pagesOcred: number;
  reviewQueue: number;
  gazettesProcessed: number;
  gazettesTotal: number;
  latestGazetteName: string | null;
  latestGazetteRows: number | null;
  latestGazetteAt: string | null;
};

export const api = {
  searchTrademarks: (p: SearchParams, init?: RequestInit) =>
    json<TrademarkListResponse>(`/api/v1/trademarks?${qs(p)}`, init),
  scoredSearch: (p: ScoredSearchParams) => json<SearchResults>(`/api/v1/search/trademarks?${qs(p)}`),
  getTrademark: (id: string) => json<Trademark>(`/api/v1/trademarks/${id}`),
  listGazettes: () => json<GazetteListResponse>(`/api/v1/gazettes`),
  getGazette: (id: string) => json<Gazette>(`/api/v1/gazettes/${id}`),
  statsOverview: () => json<StatsOverview>(`/api/v1/stats/overview`),
  statsCountries: (limit = 10) => json<CountBucket[]>(`/api/v1/stats/countries?limit=${limit}`),
  statsNiceClasses: (limit = 12) => json<CountBucket[]>(`/api/v1/stats/nice-classes?limit=${limit}`),
  facetsCountries: (filters: SearchParams, limit = 20) =>
    json<CountBucket[]>(`/api/v1/facets/countries?${qs({ ...filters, limit, offset: undefined })}`),
  facetsNiceClasses: (filters: SearchParams, limit = 45) =>
    json<CountBucket[]>(`/api/v1/facets/nice-classes?${qs({ ...filters, limit, offset: undefined })}`),
  statsTopApplicants: (limit = 10) => json<CountBucket[]>(`/api/v1/stats/top-applicants?limit=${limit}`),
  statsTopAgents: (limit = 10) => json<CountBucket[]>(`/api/v1/stats/top-agents?limit=${limit}`),
  getMark: (id: string) => json<MarkDetail>(`/api/v1/marks/${id}`),
  compare: async (markIds: string[], anchorId?: string): Promise<CompareResponse> => {
    const r = await fetch(`/api/v1/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markIds, anchorId }),
    });
    if (!r.ok) throw new Error(`Compare failed: ${r.status}`);
    return r.json();
  },
  markTimeline: (id: string) => json<TimelineEvent[]>(`/api/v1/marks/${id}/timeline`),
  markCoMarks: (id: string, limit = 6) => json<CoMark[]>(`/api/v1/marks/${id}/co-marks?limit=${limit}`),
  markSimilar: (id: string, limit = 4) => json<SimilarMark[]>(`/api/v1/marks/${id}/similar?limit=${limit}`),
  markApplicantStats: (id: string) => json<ApplicantStats>(`/api/v1/marks/${id}/applicant-stats`),
  markInidFields: (id: string) => json<InidMarker[]>(`/api/v1/marks/${id}/inid-fields`),
  todayDigest: () => json<TodayDigest>(`/api/v1/today/digest`),
  findings: () => json<Finding[]>(`/api/v1/findings`),
  oppositionWindows: (status: "open" | "closed" = "open", limit = 20) =>
    json<OppositionWindow[]>(`/api/v1/opposition-windows?status=${status}&limit=${limit}`),
  watchlists: () => json<Watchlist[]>(`/api/v1/watchlists`),
  watchlistFindings: (id: string, limit = 12) => json<Trademark[]>(`/api/v1/watchlists/${id}/findings?limit=${limit}`),
  createWatchlist: async (body: { name: string; client?: string; matter?: string; query: WatchQuery; queryDesc?: string }) => {
    const r = await fetch(`/api/v1/watchlists`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`Create failed: ${r.status}`);
    return r.json() as Promise<Watchlist>;
  },
  deleteWatchlist: async (id: string) => {
    const r = await fetch(`/api/v1/watchlists/${id}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(`Delete failed: ${r.status}`);
  },
  pipelineStats: () => json<PipelineStats>(`/api/v1/stats/pipeline`),
  adminCheck: () => json<AdminCheck>(`/api/v1/admin/check`),
  uploadGazette: async (file: File): Promise<Gazette> => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`/api/v1/gazettes`, { method: "POST", body: fd });
    if (!r.ok) {
      const d = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(d.detail || `Upload failed: ${r.status}`);
    }
    return r.json();
  },
};

// Country code → display name + flag emoji. Keeps the UI simple without
// pulling in a full ISO-3166 list (we only need to render what we have).
export const COUNTRIES: Record<string, { name: string; flag: string }> = {
  VN: { name: "Vietnam", flag: "🇻🇳" },
  CN: { name: "China", flag: "🇨🇳" },
  US: { name: "United States", flag: "🇺🇸" },
  KR: { name: "South Korea", flag: "🇰🇷" },
  JP: { name: "Japan", flag: "🇯🇵" },
  TW: { name: "Taiwan", flag: "🇹🇼" },
  TH: { name: "Thailand", flag: "🇹🇭" },
  SG: { name: "Singapore", flag: "🇸🇬" },
  DE: { name: "Germany", flag: "🇩🇪" },
  FR: { name: "France", flag: "🇫🇷" },
  GB: { name: "United Kingdom", flag: "🇬🇧" },
  IT: { name: "Italy", flag: "🇮🇹" },
  CH: { name: "Switzerland", flag: "🇨🇭" },
  IN: { name: "India", flag: "🇮🇳" },
  ID: { name: "Indonesia", flag: "🇮🇩" },
  MY: { name: "Malaysia", flag: "🇲🇾" },
  PH: { name: "Philippines", flag: "🇵🇭" },
  AU: { name: "Australia", flag: "🇦🇺" },
  CA: { name: "Canada", flag: "🇨🇦" },
  NL: { name: "Netherlands", flag: "🇳🇱" },
  ES: { name: "Spain", flag: "🇪🇸" },
  TR: { name: "Türkiye", flag: "🇹🇷" },
  RU: { name: "Russia", flag: "🇷🇺" },
  BR: { name: "Brazil", flag: "🇧🇷" },
  MX: { name: "Mexico", flag: "🇲🇽" },
  HK: { name: "Hong Kong", flag: "🇭🇰" },
};
export function countryDisplay(cc: string | null | undefined): { name: string; flag: string; cc: string } {
  if (!cc) return { name: "—", flag: "🌐", cc: "" };
  const c = COUNTRIES[cc];
  return c ? { ...c, cc } : { name: cc, flag: "🏳️", cc };
}

// Short Nice class labels (mirrors backend/api/v1/routes/stats.py NICE_LABELS).
export const NICE_LABELS: Record<string, string> = {
  "01": "Chemicals", "02": "Paints", "03": "Cosmetics & cleaning", "04": "Fuels",
  "05": "Pharmaceuticals", "06": "Metal goods", "07": "Machines", "08": "Hand tools",
  "09": "Software & electronics", "10": "Medical apparatus", "11": "Lighting & heating",
  "12": "Vehicles", "13": "Firearms", "14": "Jewelry", "15": "Musical instruments",
  "16": "Paper goods & printing", "17": "Rubber & plastics", "18": "Leather goods",
  "19": "Building materials", "20": "Furniture", "21": "Household utensils",
  "22": "Ropes & textiles", "23": "Yarns", "24": "Fabrics", "25": "Clothing & footwear",
  "26": "Lace & embroidery", "27": "Carpets", "28": "Toys & sporting goods",
  "29": "Meat, dairy, processed food", "30": "Coffee, foodstuffs", "31": "Agricultural products",
  "32": "Non-alcoholic beverages", "33": "Alcoholic beverages", "34": "Tobacco",
  "35": "Services & advertising", "36": "Insurance & finance", "37": "Construction & repair",
  "38": "Telecommunications", "39": "Transport & storage", "40": "Materials treatment",
  "41": "Education & entertainment", "42": "Scientific services", "43": "Food & lodging services",
  "44": "Medical services", "45": "Legal & security services",
};
