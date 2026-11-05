/**
 * Typed client for the Fixify API.
 *
 * The browser only ever talks to its own origin: Next.js rewrites /api/v1/* to FastAPI, so the
 * HttpOnly session cookies stay first-party. Unsafe requests carry the session-bound CSRF token
 * (read from the fixify_csrf cookie). A 401 triggers one token refresh and one retry.
 */

export type RunStatus = "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type CheckStatus = "passed" | "failed" | "skipped" | "error";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type FixStatus = "pending_review" | "approved" | "rejected" | "applied" | "failed_validation" | "superseded";

export const SEVERITIES: readonly Severity[] = ["critical", "high", "medium", "low", "info"];
export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set(["completed", "completed_with_errors", "failed", "cancelled"]);
export const ACTIVE_JOB: ReadonlySet<JobStatus> = new Set(["queued", "running"]);

export type User = {
  id: string;
  email: string;
  display_name: string;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type SessionInfo = {
  id: string;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  current: boolean;
};

export type LatestScan = { id: string; status: RunStatus; created_at: string; finished_at: string | null; findings_count: number };

export type Project = {
  id: string;
  name: string;
  description: string | null;
  scan_max_links: number | null;
  website_url: string;
  repo_full_name: string | null;
  github_repo_id: string | null;
  default_branch: string | null;
  verified_host: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
  latest_scan?: LatestScan | null;
};

export type ProjectInput = {
  name?: string;
  website_url?: string;
  description?: string | null;
  scan_max_links?: number | null;
  repo_full_name?: string | null;
  default_branch?: string | null;
};

export type SeverityCounts = Record<Severity, number>;

export type RunSummary = {
  id: string;
  project_id: string;
  status: RunStatus;
  trigger: "manual" | "scheduled";
  target_url: string;
  final_url: string | null;
  failure_reason: string | null;
  attempts: number;
  max_links: number;
  checks_total: number;
  checks_passed: number;
  checks_failed: number;
  checks_errored: number;
  checks_skipped: number;
  findings_count: number;
  severity_counts: SeverityCounts;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
};

export type CheckResult = {
  id: string;
  name: string;
  check_type: string;
  status: CheckStatus;
  target_url: string;
  summary: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  details: Record<string, unknown>;
};

export type Artifact = {
  id: string;
  kind: string;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  created_at: string;
  url: string;
};

export type RunDetail = RunSummary & { checks: CheckResult[]; artifacts: Artifact[] };

export type Finding = {
  id: string;
  test_run_id: string;
  project_id: string;
  check_type: string;
  finding_type: string;
  title: string;
  description: string;
  severity: Severity;
  confidence: "confirmed" | "suspected";
  affected_url: string | null;
  http_status: number | null;
  fingerprint: string;
  artifact_id: string | null;
  first_detected_at: string;
  created_at: string;
};

export type FindingDetail = Finding & { evidence: Record<string, unknown>; artifact: Artifact | null };

export type ComparisonFinding = { fingerprint: string; title: string; severity: Severity; affected_url: string | null; finding_id: string };
export type RunComparison = { run_id: string; previous_run_id: string | null; new: ComparisonFinding[]; resolved: ComparisonFinding[]; unchanged_count: number };

export type DashboardSummary = { project_count: number; scan_count: number; active_scan_count: number; latest_findings_count: number };

export type Job = {
  id: string;
  kind: "analyze_finding" | "generate_fix" | "create_pull_request";
  status: JobStatus;
  project_id: string;
  subject_id: string;
  result_id: string | null;
  error: string | null;
  attempts: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AIStatus = { available: boolean; provider: string | null; model: string | null };

export type Analysis = {
  id: string;
  finding_id: string;
  summary: string;
  technical_explanation: string;
  root_cause: string;
  user_impact: string;
  why_it_matters: string;
  recommended_solution: string;
  fix_complexity: "trivial" | "small" | "medium" | "large";
  confidence: "low" | "medium" | "high";
  suggested_locations: { path: string; reason: string }[];
  evidence_refs: string[];
  related_finding_ids: string[];
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
};

export type FindingAIState = { ai: AIStatus; analysis: Analysis | null; active_job: Job | null; last_job: Job | null };

export type GitHubStatus = {
  configured: boolean;
  connected: boolean;
  status: string | null;
  login: string | null;
  avatar_url: string | null;
  scopes: string[];
  connected_at: string | null;
};

export type Repository = {
  id: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  description: string | null;
  html_url: string | null;
  can_push: boolean;
  updated_at: string | null;
};

export type RepositoryTree = { repo_full_name: string; branch: string; commit_sha: string; truncated: boolean; files: { path: string; size: number }[] };

export type FileChange = { path: string; language: string; start_line: number; original: string; proposed: string; edits: { path: string; original: string; replacement: string; reason: string }[] };
export type Review = { id: string; action: "comment" | "approve" | "reject" | "reopen"; comment: string | null; user_id: string | null; created_at: string };
export type PullRequest = {
  id: string;
  status: "creating" | "open" | "closed" | "merged" | "failed";
  repo_full_name: string;
  branch_name: string;
  base_branch: string;
  commit_sha: string | null;
  number: number | null;
  url: string | null;
  error: string | null;
  last_synced_at: string | null;
  created_at: string;
};

export type FixSummary = {
  id: string;
  project_id: string;
  finding_id: string;
  status: FixStatus;
  version: number;
  title: string;
  confidence: "low" | "medium" | "high";
  validation_status: "passed" | "failed" | "not_available";
  repo_full_name: string;
  base_branch: string;
  files: string[];
  created_at: string;
  updated_at: string;
};

export type FixDetail = FixSummary & {
  analysis_id: string | null;
  parent_id: string | null;
  base_commit_sha: string;
  explanation: string;
  impact: string;
  validation_messages: string[];
  changes: FileChange[];
  provider: string;
  model: string;
  reviewed_at: string | null;
  reviews: Review[];
  pull_request: PullRequest | null;
  finding_title: string | null;
  finding_severity: Severity | null;
};

export type Notification = { id: string; kind: string; title: string; body: string; link: string | null; project_id: string | null; read_at: string | null; created_at: string };
export type NotificationList = { items: Notification[]; unread_count: number };
export type NotificationPreference = { kind: string; label: string; enabled: boolean };

export type Schedule = {
  project_id: string;
  enabled: boolean;
  frequency: "daily" | "weekly" | "custom";
  hour_utc: number;
  weekday: number | null;
  interval_hours: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_id: string | null;
  last_outcome: string | null;
};
export type Verification = {
  required: boolean;
  verified: boolean;
  host: string;
  verified_at: string | null;
  method: "meta" | "file" | null;
  token: string;
  meta_tag: string;
  file_url: string;
};

export type ScheduleInput = Pick<Schedule, "enabled" | "frequency" | "hour_utc" | "weekday" | "interval_hours">;

export type DailyPoint = { date: string; scans: number; failed_scans: number; new_findings: number; resolved_findings: number; severity: SeverityCounts; health: number | null };
export type Analytics = {
  days: number;
  project_count: number;
  scan_count: number;
  finished_scan_count: number;
  failed_scan_count: number;
  active_scan_count: number;
  average_duration_ms: number | null;
  current_findings: SeverityCounts;
  new_findings: number;
  resolved_findings: number;
  open_fix_proposals: number;
  open_pull_requests: number;
  daily: DailyPoint[];
  projects: { project_id: string; name: string; health: number | null; latest_scan_id: string | null; latest_scan_at: string | null; findings: number }[];
  recent_scans: { id: string; project_id: string; project_name: string; status: RunStatus; trigger: string; created_at: string; duration_ms: number | null; findings: number; critical: number; high: number }[];
  health_formula: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const API_BASE = "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
export const SIGNED_OUT_EVENT = "fixify:signed-out";

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(/(?:^|;\s*)fixify_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

let refreshing: Promise<boolean> | null = null;

/** One refresh at a time, shared by every request that hit a 401. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "same-origin" })
    .then((response) => response.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
        const message = String((detail[0] as { msg: unknown }).msg).replace(/^Value error, /, "");
        return message || "Please check the form and try again.";
      }
    }
  } catch {
    // not JSON
  }
  if (response.status === 429) return "Too many requests. Please wait a moment and try again.";
  if (response.status >= 500) return "The server ran into a problem. Please try again.";
  return `The request failed (${response.status}).`;
}

type RequestOptions = { method?: string; body?: unknown; signal?: AbortSignal };

export async function request<T>(path: string, options: RequestOptions = {}, retry = true): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) {
    const token = csrfToken();
    if (token) headers["X-CSRF-Token"] = token;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: "same-origin",
      cache: "no-store",
      signal: options.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Could not reach the Fixify API. Check that the backend is running.", 0);
  }

  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(path, options, false);
    if (typeof window !== "undefined") window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const enc = encodeURIComponent;
const qs = (params: Record<string, string | number | boolean | null | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const authApi = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) => request<User>("/auth/login", { method: "POST", body: { email, password } }),
  register: (body: { email: string; password: string; display_name: string }) => request<User>("/auth/register", { method: "POST", body }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  verifyEmail: (token: string) => request<User>("/auth/verify-email", { method: "POST", body: { token } }),
  resendVerification: () => request<{ message: string }>("/auth/resend-verification", { method: "POST" }),
  forgotPassword: (email: string) => request<{ message: string }>("/auth/forgot-password", { method: "POST", body: { email } }),
  resetPassword: (token: string, password: string) => request<{ message: string }>("/auth/reset-password", { method: "POST", body: { token, password } }),
};

export const accountApi = {
  update: (display_name: string) => request<User>("/users/me", { method: "PATCH", body: { display_name } }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>("/users/me/password", { method: "POST", body: { current_password, new_password } }),
  remove: (password: string) => request<void>("/users/me", { method: "DELETE", body: { password } }),
  sessions: () => request<SessionInfo[]>("/users/me/sessions"),
  revokeSession: (id: string) => request<void>(`/users/me/sessions/${enc(id)}`, { method: "DELETE" }),
  revokeOthers: () => request<{ message: string }>("/users/me/sessions/revoke-others", { method: "POST" }),
};

export const projectApi = {
  list: (search?: string) => request<Project[]>(`/projects${qs({ limit: 100, search })}`),
  get: (id: string) => request<Project>(`/projects/${enc(id)}`),
  create: (body: ProjectInput) => request<Project>("/projects", { method: "POST", body }),
  update: (id: string, body: ProjectInput) => request<Project>(`/projects/${enc(id)}`, { method: "PATCH", body }),
  remove: (id: string) => request<void>(`/projects/${enc(id)}`, { method: "DELETE" }),
  schedule: (id: string) => request<Schedule | null>(`/projects/${enc(id)}/schedule`),
  saveSchedule: (id: string, body: ScheduleInput) => request<Schedule>(`/projects/${enc(id)}/schedule`, { method: "PUT", body }),
  deleteSchedule: (id: string) => request<void>(`/projects/${enc(id)}/schedule`, { method: "DELETE" }),
  connectRepository: (id: string, repo_full_name: string, branch?: string) =>
    request<Project>(`/projects/${enc(id)}/repository`, { method: "PUT", body: { repo_full_name, branch: branch || null } }),
  disconnectRepository: (id: string) => request<Project>(`/projects/${enc(id)}/repository`, { method: "DELETE" }),
  verification: (id: string) => request<Verification>(`/projects/${enc(id)}/verification`),
  checkVerification: (id: string) => request<Verification>(`/projects/${enc(id)}/verification/check`, { method: "POST" }),
  tree: (id: string, query?: string) => request<RepositoryTree>(`/projects/${enc(id)}/repository/tree${qs({ query, limit: 200 })}`),
};

export const scanApi = {
  start: (projectId: string) => request<RunSummary>(`/projects/${enc(projectId)}/scans`, { method: "POST", body: {} }),
  forProject: (projectId: string, limit = 20) => request<RunSummary[]>(`/projects/${enc(projectId)}/scans${qs({ limit })}`),
  recent: (limit = 50) => request<RunSummary[]>(`/scans${qs({ limit })}`),
  get: (runId: string) => request<RunDetail>(`/scans/${enc(runId)}`),
  cancel: (runId: string) => request<RunSummary>(`/scans/${enc(runId)}/cancel`, { method: "POST" }),
  findings: (runId: string, severity?: Severity) => request<Finding[]>(`/scans/${enc(runId)}/findings${qs({ limit: 100, severity })}`),
  comparison: (runId: string) => request<RunComparison>(`/scans/${enc(runId)}/comparison`),
  summary: () => request<DashboardSummary>("/scans/summary"),
  artifactUrl: (artifact: Artifact) => artifact.url,
};

export const findingApi = {
  list: (params: { severity?: Severity; latestOnly?: boolean } = {}) =>
    request<Finding[]>(`/findings${qs({ severity: params.severity, latest_only: params.latestOnly ?? true, limit: 200 })}`),
  forProject: (projectId: string) => request<Finding[]>(`/projects/${enc(projectId)}/findings${qs({ limit: 100 })}`),
  get: (id: string) => request<FindingDetail>(`/findings/${enc(id)}`),
  ai: (id: string) => request<FindingAIState>(`/findings/${enc(id)}/ai`),
  analyze: (id: string) => request<Job>(`/findings/${enc(id)}/analysis`, { method: "POST" }),
  generateFix: (id: string, body: { file_paths?: string[]; instructions?: string }) =>
    request<Job>(`/findings/${enc(id)}/fixes`, { method: "POST", body }),
};

export const aiApi = { status: () => request<AIStatus>("/ai/status") };

export const jobApi = {
  get: (id: string) => request<Job>(`/jobs/${enc(id)}`),
  forSubject: (subjectId: string) => request<Job[]>(`/jobs${qs({ subject_id: subjectId, limit: 10 })}`),
  active: () => request<Job[]>(`/jobs${qs({ active: true, limit: 50 })}`),
};

export const fixApi = {
  list: (params: { project_id?: string; finding_id?: string; status?: FixStatus } = {}) => request<FixSummary[]>(`/fixes${qs(params)}`),
  get: (id: string) => request<FixDetail>(`/fixes/${enc(id)}`),
  review: (id: string, action: Review["action"], comment?: string) =>
    request<FixDetail>(`/fixes/${enc(id)}/reviews`, { method: "POST", body: { action, comment: comment || null } }),
  regenerate: (id: string, instructions?: string) => request<Job>(`/fixes/${enc(id)}/regenerate`, { method: "POST", body: { instructions: instructions || null } }),
  createPullRequest: (id: string) => request<Job>(`/fixes/${enc(id)}/pull-request`, { method: "POST" }),
  refreshPullRequest: (id: string) => request<PullRequest>(`/fixes/${enc(id)}/pull-request/refresh`, { method: "POST" }),
};

export const githubApi = {
  status: () => request<GitHubStatus>("/github/status"),
  connect: () => request<{ authorize_url: string }>("/github/connect", { method: "POST" }),
  complete: (code: string, state: string) => request<GitHubStatus>("/github/complete", { method: "POST", body: { code, state } }),
  disconnect: () => request<void>("/github/connection", { method: "DELETE" }),
  repositories: () => request<Repository[]>("/github/repositories"),
  branches: (fullName: string) => {
    const [owner, name] = fullName.split("/");
    return request<string[]>(`/github/repositories/${enc(owner)}/${enc(name)}/branches`);
  },
};

export const notificationApi = {
  list: (unreadOnly = false, limit = 30) => request<NotificationList>(`/notifications${qs({ unread_only: unreadOnly, limit })}`),
  read: (id: string) => request<void>(`/notifications/${enc(id)}/read`, { method: "POST" }),
  readAll: () => request<{ updated: number }>("/notifications/read-all", { method: "POST" }),
  preferences: () => request<NotificationPreference[]>("/notifications/preferences"),
  savePreferences: (notifications: Record<string, boolean>) =>
    request<NotificationPreference[]>("/notifications/preferences", { method: "PUT", body: { notifications } }),
};

export const analyticsApi = {
  overview: (days = 30, projectId?: string) => request<Analytics>(`/analytics/overview${qs({ days, project_id: projectId })}`),
};
