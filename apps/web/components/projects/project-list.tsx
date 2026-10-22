"use client";

import Link from "next/link";
import { ExternalLink, FolderPlus, Trash2 } from "lucide-react";
import type { Project } from "@/lib/api";
import { formatDate, getHostname } from "@/lib/utils";

export function ProjectList({ projects, onDelete }: {
  projects: Project[];
  onDelete?: (project: Project) => void;
}) {
  if (projects.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon"><FolderPlus size={21} /></span>
        <h3>Your workspace is ready</h3>
        <p>Add your first website to keep its project details in one place. Test runs and findings will arrive in a later step.</p>
        <Link href="/projects/new" className="button">Create your first project</Link>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="project-table">
        <thead>
          <tr><th>Project</th><th>Repository</th><th>Created</th><th aria-label="Actions" /></tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td>
                <Link className="project-name-link" href={`/projects/${project.id}`}>{project.name}</Link>
                <span className="project-host">{getHostname(project.website_url)}</span>
              </td>
              <td>
                <span className="connection-badge"><span className="status-dot" />Not connected</span>
                {project.repo_full_name && <span className="project-host">{project.repo_full_name} · reference only</span>}
              </td>
              <td>{formatDate(project.created_at)}</td>
              <td className="table-actions">
                <a className="table-action" href={project.website_url} target="_blank" rel="noreferrer" aria-label={`Open ${project.name} website`}>
                  <ExternalLink size={15} />
                </a>
                {onDelete && (
                  <button className="table-action" onClick={() => onDelete(project)} aria-label={`Delete ${project.name}`}>
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
