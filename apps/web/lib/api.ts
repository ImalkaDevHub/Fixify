import type { ProjectCreateInput } from "@/lib/schemas";

export type RunStatus = "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type CheckStatus = "passed" | "failed" | "skipped" | "error";

export const SEVERITIES: readonly Severity[] = ["critical", "high", "medium", "low", "info"];
export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "completed_with_errors",
  "failed",
  "cancelled",
]);

export type LatestScan = {
  id: string;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  findings_count: number;
};

export type Project = {
  id: string;
  name: string;
  website_url: string;
  repo_full_name: string | null;
  github_repo_id: string | null;
  default_branch: string | null;
  created_at: string;
  updated_at: string;
  latest_scan?: LatestScan | null;
};

export type ScanQueued = {
  id: string;
  status: RunStatus;
  project_id: string;
  target_url: string;
  created_at: string;
};

export type RunSummary = {
  id: string;
  project_id: string;
  status: RunStatus;
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
  severity_counts: Record<Severity, number>;
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

export type ComparisonFinding = {
  fingerprint: string;
  title: string;
  severity: Severity;
  affected_url: string | null;
  finding_id: string;
};

export type RunComparison = {
  run_id: string;
  previous_run_id: string | null;
  new: ComparisonFinding[];
  resolved: ComparisonFinding[];
  unchanged_count: number;
};

export type DashboardSummary = {
  project_count: number;
  scan_count: number;
  active_scan_count: number;
  latest_findings_count: number;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1")
  .replace(/\/+$/, "");

/** Absolute URL for an artifact path returned by the API ("/api/v1/scans/..."). */
export function artifactUrl(artifact: Artifact): string {
  const origin = new URL(apiBaseUrl).origin;
  return `${origin}${artifact.url}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Could not reach the Fixify API. Check that the backend is running.", 0);
  }

  if (!response.ok) {
    let message = `The request failed (${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        message = body.detail;
      } else if (Array.isArray((body as { detail?: unknown }).detail)) {
        message = "Please check the project details and try again.";
      }
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const projectApi = {
  list: (limit = 100, offset = 0) =>
    request<Project[]>(`/projects?limit=${limit}&offset=${offset}`),
  count: async () => {
    const response = await request<{ total: number }>("/projects/count");
    return response.total;
  },
  create: (project: ProjectCreateInput) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(project) }),
  get: (projectId: string) => request<Project>(`/projects/${encodeURIComponent(projectId)}`),
  delete: (projectId: string) =>
    request<void>(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" }),
};

export const scanApi = {
  start: (projectId: string) =>
    request<ScanQueued>(`/projects/${encodeURIComponent(projectId)}/scans`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  list: (projectId: string, limit = 10, offset = 0) =>
    request<RunSummary[]>(
      `/projects/${encodeURIComponent(projectId)}/scans?limit=${limit}&offset=${offset}`,
    ),
  get: (runId: string) => request<RunDetail>(`/scans/${encodeURIComponent(runId)}`),
  findings: (runId: string, severity?: Severity) =>
    request<Finding[]>(
      `/scans/${encodeURIComponent(runId)}/findings?limit=100${severity ? `&severity=${severity}` : ""}`,
    ),
  comparison: (runId: string) =>
    request<RunComparison>(`/scans/${encodeURIComponent(runId)}/comparison`),
  finding: (findingId: string) =>
    request<FindingDetail>(`/findings/${encodeURIComponent(findingId)}`),
  summary: () => request<DashboardSummary>("/scans/summary"),
};
