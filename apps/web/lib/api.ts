import type { ProjectCreateInput } from "@/lib/schemas";

export type Project = {
  id: string;
  name: string;
  website_url: string;
  repo_full_name: string | null;
  github_repo_id: string | null;
  default_branch: string | null;
  created_at: string;
  updated_at: string;
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
