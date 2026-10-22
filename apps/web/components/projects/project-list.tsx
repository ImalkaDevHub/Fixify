"use client";

import Link from "next/link";
import { ExternalLink, FolderPlus, Trash2 } from "lucide-react";
import type { Project, RunStatus } from "@/lib/api";
import { RunStatusBadge } from "@/components/scans/badges";
import { formatDate, getHostname } from "@/lib/utils";

const finishedWithResults = (status: RunStatus) => status === "completed" || status === "completed_with_errors";

export function ProjectList({ projects, onDelete, deletingId }: {
  projects: Project[];
  onDelete?: (project: Project) => void;
  deletingId?: string | null;
}) {
  if (projects.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon"><FolderPlus size={21} /></span>
        <h3>Your workspace is ready</h3>
        <p>Add your first website to keep its project details in one place. Then run a scan from the project page.</p>
        <Link href="/projects/new" className="button">Create your first project</Link>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="project-table">
        <thead>
          <tr><th>Project</th><th>Latest scan</th><th>Last scanned</th><th>Findings</th><th>Repository</th><th aria-label="Actions" /></tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td>
                <Link className="project-name-link" href={`/projects/${project.id}`}>{project.name}</Link>
                <span className="project-host">{getHostname(project.website_url)}</span>
              </td>
              <td>{project.latest_scan ? <Link href={`/scans/${project.latest_scan.id}`}><RunStatusBadge status={project.latest_scan.status} /></Link> : <span className="muted-small">Never scanned</span>}</td>
              <td>{project.latest_scan ? formatDate(project.latest_scan.finished_at ?? project.latest_scan.created_at) : "—"}</td>
              <td>{project.latest_scan && finishedWithResults(project.latest_scan.status) ? project.latest_scan.findings_count : "—"}</td>
              <td>
                <span className="connection-badge"><span className="status-dot" />Not connected</span>
                {project.repo_full_name && <span className="project-host">{project.repo_full_name} · reference only</span>}
              </td>
              <td className="table-actions">
                <a className="table-action" href={project.website_url} target="_blank" rel="noreferrer" aria-label={`Open ${project.name} website`}>
                  <ExternalLink size={15} />
                </a>
                {onDelete && (
                  <button className="table-action" onClick={() => onDelete(project)} disabled={deletingId === project.id} aria-label={`Delete ${project.name}`}>
                    <Trash2 size={15} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
