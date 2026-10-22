"use client";

import Link from "next/link";
import { ArrowLeft, ExternalLink, ScanSearch } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, projectApi, scanApi, TERMINAL_STATUSES, type Project, type RunSummary, type ScanQueued } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { formatDate, formatDateTime, formatDuration } from "@/lib/utils";
import { RunStatusBadge } from "@/components/scans/badges";
import { SeverityCounts } from "@/components/scans/severity-counts";

const isActive = (run: RunSummary) => !TERMINAL_STATUSES.has(run.status);

export function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    projectApi.get(projectId).then((item) => {
      if (active) setProject(item);
    }).catch((reason: unknown) => {
      if (!active) return;
      // The API answers 422 for a malformed project ID, which is also "not found" to the user.
      const notFound = reason instanceof ApiError && (reason.status === 404 || reason.status === 422);
      setError(notFound ? "This project could not be found." : reason instanceof ApiError ? reason.message : "Unable to load this project.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
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
      <ProjectScans project={project} />
    </main>
  );
}

function ProjectScans({ project }: { project: Project }) {
  const fetchRuns = useCallback(() => scanApi.list(project.id, 10), [project.id]);
  const runs = usePolling(fetchRuns, {
    intervalMs: 3000,
    maxDurationMs: 15 * 60_000,
    isDone: (items) => !items.some(isActive),
  });
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [queued, setQueued] = useState<ScanQueued | null>(null);

  async function startScan() {
    setStarting(true);
    setStartError(null);
    setQueued(null);
    try {
      setQueued(await scanApi.start(project.id));
      runs.refresh();
    } catch (reason) {
      setStartError(reason instanceof ApiError ? reason.message : "The scan could not be started.");
    } finally {
      setStarting(false);
    }
  }

  const history = runs.data ?? [];
  const latest = history[0];
  const scanInProgress = history.some(isActive);
  const loadError = runs.error instanceof ApiError ? runs.error.message : runs.error ? "Unable to load scans." : null;

  return (
    <>
      <div className="detail-grid">
        <section className="detail-card">
          <h2>Project details</h2>
          <div className="detail-row"><span className="detail-label">Website</span><a className="detail-value detail-link" href={project.website_url} target="_blank" rel="noreferrer">{project.website_url}</a></div>
          <div className="detail-row"><span className="detail-label">Repository reference</span><span className="detail-value">{project.repo_full_name ?? "None"}</span></div>
          <div className="detail-row"><span className="detail-label">GitHub connection</span><span className="detail-value">Not connected</span></div>
          <div className="detail-row"><span className="detail-label">Default branch</span><span className="detail-value">{project.default_branch ?? "—"}</span></div>
          <div className="detail-row"><span className="detail-label">Created</span><span className="detail-value">{formatDate(project.created_at)}</span></div>
        </section>
        <section className="detail-card" aria-labelledby="scan-title">
          <h2 id="scan-title">Website scan</h2>
          {runs.loading && !runs.data ? <div className="loading-state" role="status">Loading scans…</div>
            : latest ? (
              <div className="latest-scan">
                <div className="latest-scan-top"><RunStatusBadge status={latest.status} /><span className="muted-small">{formatDateTime(latest.created_at)}</span></div>
                {latest.status === "queued" && <p className="muted-small">Waiting for the scan worker to pick this scan up.</p>}
                {latest.status === "running" && <p className="muted-small">A headless browser is checking the website now.</p>}
                {TERMINAL_STATUSES.has(latest.status) && latest.status !== "cancelled" && latest.status !== "failed" && (
                  <>
                    <p className="latest-scan-count"><strong>{latest.findings_count}</strong> {latest.findings_count === 1 ? "finding" : "findings"} · {latest.checks_passed}/{latest.checks_total} checks passed</p>
                    <SeverityCounts counts={latest.severity_counts} />
                  </>
                )}
                {latest.failure_reason && <p className="muted-small">{latest.failure_reason}</p>}
                <Link className="text-link" href={`/scans/${latest.id}`}>Open scan report</Link>
              </div>
            ) : !loadError && (
              <div className="coming-soon">
                <strong><ScanSearch size={15} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Not scanned yet</strong>
                Run a scan to open this website in a headless browser and record real errors, failed requests, broken links, and a screenshot.
              </div>
            )}
          {startError && <div className="error-box" role="alert">{startError}</div>}
          {queued && !startError && <p className="success-note" role="status">Scan queued ({queued.status}). This page updates automatically.</p>}
          <button className="button scan-start" onClick={startScan} disabled={starting || scanInProgress} aria-describedby="scan-hint">
            <ScanSearch size={15} />{starting ? "Starting…" : scanInProgress ? "Scan in progress…" : "Run scan"}
          </button>
          <p id="scan-hint" className="field-hint">Only scan websites you are authorized to test. Private and local network addresses are blocked.</p>
        </section>
      </div>

      <section className="panel history-panel" aria-labelledby="history-title">
        <div className="panel-header"><div><div className="panel-title" id="history-title">Scan history</div><div className="panel-caption">Most recent first</div></div></div>
        {loadError ? <div className="error-box panel-error" role="alert">{loadError} <button className="inline-retry" onClick={runs.refresh}>Try again</button></div>
          : history.length === 0 ? <div className="loading-state">{runs.loading ? "Loading…" : "No scans yet."}</div>
            : <ScanHistoryTable runs={history} />}
        {runs.gaveUp && !loadError && <p className="muted-small panel-note">Automatic updates stopped. <button className="inline-retry" onClick={runs.refresh}>Refresh</button></p>}
      </section>
    </>
  );
}

function ScanHistoryTable({ runs }: { runs: RunSummary[] }) {
  return (
    <div className="table-wrap">
      <table className="project-table">
        <thead><tr><th>Started</th><th>Status</th><th>Checks passed</th><th>Findings</th><th>Duration</th><th aria-label="Actions" /></tr></thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>{formatDateTime(run.started_at ?? run.created_at)}</td>
              <td><RunStatusBadge status={run.status} /></td>
              <td>{run.checks_total ? `${run.checks_passed}/${run.checks_total}` : "—"}</td>
              <td>{TERMINAL_STATUSES.has(run.status) && run.checks_total ? run.findings_count : "—"}</td>
              <td>{formatDuration(run.duration_ms)}</td>
              <td className="table-actions"><Link className="text-link" href={`/scans/${run.id}`}>View</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
