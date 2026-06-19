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

export type AdminCheck = { isAdmin: boolean; role: "admin" | "editor" | "viewer"; reason: string };

export type MadridEnrichmentStats = {
  unique_irns: number;
  validated: number;
  remaining: number;
  pct_complete: number; // 0..1
  vn_granted: number;
  by_category: Record<string, number>;
};

export type MadridSweepControl = {
  status: "idle" | "running" | "paused" | "stopping";
  cap: number | null;
  delay: number;
  jitter: number;
  chunk_size: number;
  processed: number;
  ok: number;
  failed: number;
  current_irn: string | null;
  next_irn: string | null;
  last_error: string | null;
  started_at: string | null;
  updated_at: string;
};

export type SweepCadence = { cap?: number | null; delay?: number; jitter?: number; chunk_size?: number };

export type Trademark = {
  id: string;
  gazette_id: string;
  record_type: "A" | "B_domestic" | "B_madrid";
  /** Derived, correct-by-construction classification (STORED generated column).
   * Prefer this over `record_type` for any display/label decision — record_type
   * mislabels the 2,605 Madrid registrations (111-only, no 210) as B_domestic,
   * whereas mark_category distinguishes them. See markCategoryMeta(). */
  mark_category:
    | "domestic_application"
    | "domestic_registration"
    | "madrid_registration"
    | "madrid_renewal"
    | "unknown"
    | null;
  /** Identity that links a mark's rows across gazette years: COALESCE(210, 111,
   * 116) — domestic by application number, Madrid by WIPO IRN. */
  lineage_key: string | null;
  application_number: string | null;
  certificate_number: string | null;
  madrid_number: string | null;
  publication_date_441: string | null;
  publication_date_450: string | null;
  registration_date_151: string | null;
  nice_classes: string[] | null;
  nice_total: number | null;
  /** WIPO 531 figurative-element classification codes (e.g. "26.1.2"). */
  vienna_codes: string[] | null;
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
  /** Figurative-element codes ((531) in WIPO INID terminology). The backend
   * accepts either NN.NN or NN.NN.NN form and normalises leading zeros, so
   * `01.01` and `1.1` match the same rows. */
  vienna_codes?: string[];
  record_type?: string;
  /** Derived classification filter — preferred over record_type. One of
   * domestic_application | domestic_registration | madrid_registration |
   * madrid_renewal | unknown. */
  mark_category?: string;
  applicant_type?: string;
  /** Free-text or facet-picked applicant name (substring, case-insensitive). */
  applicant?: string;
  year?: number;
  month?: number;
  gazette_id?: string;
  ip_agency?: string;
  /** Madrid designated jurisdiction (ISO2). Matches marks whose Madrid record
   * covers this country. "VN" = protected/processed in Vietnam. */
  designated_country?: string;
  /** VN protection status: granted | pending | refused. */
  vn_status?: string;
  /** ISO date strings (YYYY-MM-DD). Filter by INID (151) certificate issue
   * date. Only B-files (domestic + Madrid registrations) carry this, so
   * A-files are naturally excluded by any grant-date filter. */
  grant_date_from?: string;
  grant_date_to?: string;
  limit?: number;
  offset?: number;
};

export type StatsOverview = {
  total: number;
  by_record_type: Record<string, number>;
  by_mark_category: Record<string, number>;
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
  // Lazy import to avoid pulling auth into the module-load graph for tests
  // that don't go through the API. Also dodges a potential circular-import
  // with auth.ts if it ever needs `api` for something.
  const { getAccessToken, refresh } = await import("./auth");

  const withAuth = (): RequestInit => {
    const token = getAccessToken();
    const headers = new Headers(init?.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return { ...init, headers, credentials: "include" };
  };

  let r = await fetch(url, withAuth());
  // 401 → try to refresh the access token once, then retry. If refresh fails
  // (no valid refresh cookie, token revoked), redirect to /login.
  if (r.status === 401 && !url.includes("/auth/")) {
    const user = await refresh();
    if (user) {
      r = await fetch(url, withAuth());
    } else if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      // Preserve return path so the user lands back where they were.
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?next=${next}`;
      // Throw to short-circuit any caller; navigation is in flight.
      throw new Error("Authentication required");
    }
  }
  if (!r.ok) {
    // FastAPI returns structured errors as `{detail: "..."}`. Surface that to
    // the caller (toast / error UI) instead of swallowing it into a bare status
    // code. .catch handles non-JSON error bodies (e.g. an HTML 502 page).
    const body = (await r.json().catch(() => null)) as { detail?: string; error?: { message?: string } } | null;
    throw new Error(body?.error?.message ?? body?.detail ?? `${url} -> ${r.status}`);
  }
  return r.json();
}

/** Authed mutation with no JSON body to parse (e.g. 204 DELETE). Same
 *  Authorization + credentials + one-shot 401-refresh as json(); kept separate
 *  because json() always parses a body. Without this, write calls that used
 *  raw fetch() never sent the bearer token and 401'd while "logged in". */
async function mutateVoid(url: string, init: RequestInit): Promise<void> {
  const { getAccessToken, refresh } = await import("./auth");
  const withAuth = (): RequestInit => {
    const headers = new Headers(init.headers);
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return { ...init, headers, credentials: "include" };
  };
  let r = await fetch(url, withAuth());
  if (r.status === 401) {
    const user = await refresh();
    if (user) r = await fetch(url, withAuth());
  }
  if (!r.ok && r.status !== 204) throw new Error(`${url} -> ${r.status}`);
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
  /** Per-matter similarity weight overrides (keys: phonetic/visual/class/vienna).
   *  null → default weight profile. Stored raw; normalised server-side at use. */
  weights: Record<string, number> | null;
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
  vienna_codes_mode?: NiceMode;
  sort?: SortKey;
};

/** WIPO Madrid Monitor enrichment for a Madrid mark, joined from
 * `madrid_records` on `irn == trademarks.lineage_key`. Detail-only —
 * never on the lean list/search Trademark shape. */
export type MadridEnrichment = {
  irn: string;
  holder_name: string | null;
  holder_address: string | null;
  holder_country: string | null;
  holder_legal_status: string | null;
  mark_text: string | null;
  representative: string | null;
  registration_date: string | null;
  expiration_date: string | null;
  nice_classes: string[] | null;
  /** Per-class full goods & services text from WIPO, keyed by 2-digit Nice
   * class ({ "33": "Alcoholic beverages …" }). The gazette only has the bare
   * class list for Madrid marks, so this is the only source of full wording. */
  goods_services: Record<string, string> | null;
  designated_countries: string[] | null;
  basic_registration: string | null;
  language: string | null;
  vn_designated: boolean | null;
  vn_status: string | null;
  vn_grant_date: string | null;
  vn_refusal_date: string | null;
  /** WIPO per-country snapshot: { "VN": { date, status, gazette? }, ... } */
  designation_status: Record<string, { date?: string; status?: string; gazette?: string }> | null;
  /** Chronological WIPO events: [{ type, date, parties:[ISO2], gazette? }] */
  transaction_history: Array<{ type?: string; date?: string; parties?: string[]; gazette?: string }> | null;
  source_url: string | null;
  fetched_at: string | null;
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
  /** WIPO Madrid enrichment — present only for enriched Madrid marks. */
  enrichment: MadridEnrichment | null;
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

export type SimilarMark = {
  mark: Trademark;
  score: number;
  // Whether the visual signal that fed into `score` was a real pHash
  // comparison ('phash'), a typographic fallback on the wordmark text
  // ('typographic'), or no visual signal at all ('none'). The UI surfaces
  // a small annotation when visual is typographic so the user knows the
  // visual score isn't authoritative.
  visualConfidence?: "phash" | "typographic" | "none";
};

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
  viennaOverlap: number;
  composite: number;
  verdict: string;       // "Likely conflict" | "Possible conflict" | "Low risk"
  verdictTone: "stamp" | "warn" | "ok";
  // 'phash' = visual is a real perceptual-hash comparison on extracted PNGs
  // (gold standard). 'typographic' = both marks were missing logos, so the
  // visual score is a typographic JW on the wordmark text — meaningful but
  // a trademark expert should inspect the actual specimens. 'none' = no
  // visual signal at all.
  visualConfidence: "phash" | "typographic" | "none";
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
  facetsCountries: (filters: SearchParams, limit = 20, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/countries?${qs({ ...filters, limit, offset: undefined })}`, init),
  facetsNiceClasses: (filters: SearchParams, limit = 45, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/nice-classes?${qs({ ...filters, limit, offset: undefined })}`, init),
  facetsApplicants: (filters: SearchParams, limit = 20, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/applicants?${qs({ ...filters, limit, offset: undefined })}`, init),
  facetsIpAgencies: (filters: SearchParams, limit = 20, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/ip-agencies?${qs({ ...filters, limit, offset: undefined })}`, init),
  facetsMarkCategories: (filters: SearchParams, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/mark-categories?${qs({ ...filters, offset: undefined })}`, init),
  facetsVnStatus: (filters: SearchParams, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/vn-status?${qs({ ...filters, offset: undefined })}`, init),
  statsTopApplicants: (limit = 10) => json<CountBucket[]>(`/api/v1/stats/top-applicants?limit=${limit}`),
  statsTopAgents: (limit = 10) => json<CountBucket[]>(`/api/v1/stats/top-agents?limit=${limit}`),
  getMark: (id: string) => json<MarkDetail>(`/api/v1/marks/${id}`),
  compare: (markIds: string[], anchorId?: string): Promise<CompareResponse> =>
    json<CompareResponse>(`/api/v1/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markIds, anchorId }),
    }),
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
  createWatchlist: (body: { name: string; client?: string; matter?: string; query: WatchQuery; queryDesc?: string; weights?: Record<string, number> | null }) =>
    json<Watchlist>(`/api/v1/watchlists`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  updateWatchlist: (id: string, body: { name?: string; client?: string; matter?: string; query?: WatchQuery; queryDesc?: string; weights?: Record<string, number> | null }) =>
    json<Watchlist>(`/api/v1/watchlists/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteWatchlist: (id: string) => mutateVoid(`/api/v1/watchlists/${id}`, { method: "DELETE" }),
  pipelineStats: () => json<PipelineStats>(`/api/v1/stats/pipeline`),
  adminCheck: () => json<AdminCheck>(`/api/v1/admin/check`),
  adminMadridStats: () => json<MadridEnrichmentStats>(`/api/v1/admin/madrid-enrichment`),
  madridSweepStatus: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep`),
  madridSweepStart: (body: SweepCadence) =>
    json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/start`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  madridSweepPause: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/pause`, { method: "POST" }),
  madridSweepResume: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/resume`, { method: "POST" }),
  madridSweepStop: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/stop`, { method: "POST" }),
  madridSweepConfig: (body: SweepCadence) =>
    json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/config`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  uploadGazette: (file: File): Promise<Gazette> => {
    const fd = new FormData();
    fd.append("file", file);
    // No Content-Type header — the browser sets the multipart boundary itself.
    // json() attaches the bearer token + credentials + 401-refresh, which the
    // prior raw fetch() skipped (uploads 401'd while authenticated).
    return json<Gazette>(`/api/v1/gazettes`, { method: "POST", body: fd });
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

// Derived mark_category labels for the filter rail / chips (mirrors backend
// facets.py MARK_CATEGORY_LABELS). Keys are the generated-column values.
export const MARK_CATEGORY_LABELS: Record<string, string> = {
  domestic_application: "Domestic application",
  domestic_registration: "Domestic registration",
  madrid_registration: "Madrid registration",
  madrid_renewal: "Madrid renewal",
  unknown: "Unclassified",
};

// VN protection-status labels (mirrors backend VN_STATUS_LABELS in facets.py).
export const VN_STATUS_LABELS: Record<string, string> = {
  granted: "Granted in VN",
  pending: "Pending in VN",
  refused: "Refused in VN",
};

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
