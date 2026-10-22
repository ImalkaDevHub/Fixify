"use client";

import Link from "next/link";
import { ArrowLeft, ExternalLink, ScanSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, projectApi, type Project } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    projectApi.get(projectId).then(setProject).catch((reason: unknown) => {
      setError(reason instanceof ApiError && reason.status === 404 ? "This project could not be found." : reason instanceof ApiError ? reason.message : "Unable to load this project.");
    }).finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <main className="page-content"><div className="loading-state" role="status">Loading project…</div></main>;
  if (error || !project) return <main className="page-content"><Link href="/projects" className="back-link"><ArrowLeft size={14} />Back to projects</Link><div className="error-box" role="alert">{error ?? "Unable to load this project."}</div></main>;

  return (
    <main className="page-content">
      <Link href="/projects" className="back-link"><ArrowLeft size={14} />Back to projects</Link>
      <div className="page-heading">
        <div><span className="eyebrow">Project</span><h1>{project.name}</h1><p className="page-subtitle">{project.website_url}</p></div>
        <a href={project.website_url} target="_blank" rel="noreferrer" className="button button-secondary">Visit website <ExternalLink size={14} /></a>
      </div>
      <div className="detail-grid">
        <section className="detail-card">
          <h2>Project details</h2>
          <div className="detail-row"><span className="detail-label">Website</span><a className="detail-value detail-link" href={project.website_url} target="_blank" rel="noreferrer">{project.website_url}</a></div>
          <div className="detail-row"><span className="detail-label">Repository reference</span><span className="detail-value">{project.repo_full_name ?? "None"}</span></div>
          <div className="detail-row"><span className="detail-label">GitHub connection</span><span className="detail-value">Not connected</span></div>
          <div className="detail-row"><span className="detail-label">Default branch</span><span className="detail-value">{project.default_branch ?? "—"}</span></div>
          <div className="detail-row"><span className="detail-label">Created</span><span className="detail-value">{formatDate(project.created_at)}</span></div>
        </section>
        <section className="detail-card">
          <h2>Website scan</h2>
          <div className="coming-soon">
            <strong><ScanSearch size={15} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Scanning is coming soon</strong>
            Browser checks are not available in this foundation. Your website has not been scanned.
          </div>
          <button className="button scan-button" disabled title="Browser scanning will be added in a future development stage"><ScanSearch size={15} />Start a scan · Coming soon</button>
        </section>
      </div>
    </main>
  );
}
