"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  artifactUrl,
  scanApi,
  SEVERITIES,
  TERMINAL_STATUSES,
  type Finding,
  type RunComparison,
  type RunDetail,
  type Severity,
} from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { formatDateTime, formatDuration } from "@/lib/utils";
import { CheckStatusBadge, ConfidenceBadge, RunStatusBadge, SeverityBadge } from "@/components/scans/badges";
import { SeverityCounts } from "@/components/scans/severity-counts";

export function ScanDetail({ runId }: { runId: string }) {
  const fetchRun = useCallback(() => scanApi.get(runId), [runId]);
  const run = usePolling(fetchRun, {
    intervalMs: 2500,
    maxDurationMs: 15 * 60_000,
    isDone: (detail) => TERMINAL_STATUSES.has(detail.status),
  });

  const notFound = run.error instanceof ApiError && (run.error.status === 404 || run.error.status === 422);
  if (run.loading && !run.data) return <main className="page-content"><div className="loading-state" role="status">Loading scan…</div></main>;
  if (!run.data) {
    return (
      <main className="page-content">
        <Link href="/projects" className="back-link"><ArrowLeft size={14} />Back to projects</Link>
        <div className="error-box" role="alert">
          {notFound ? "This scan could not be found." : run.error instanceof ApiError ? run.error.message : "Unable to load this scan."}
          {!notFound && <button className="inline-retry" onClick={run.refresh}>Try again</button>}
        </div>
      </main>
    );
  }
  return <ScanReport detail={run.data} pollError={run.error} gaveUp={run.gaveUp} onRefresh={run.refresh} />;
}

function ScanReport({ detail, pollError, gaveUp, onRefresh }: {
  detail: RunDetail;
  pollError: unknown;
  gaveUp: boolean;
  onRefresh: () => void;
}) {
  const finished = TERMINAL_STATUSES.has(detail.status);
  const screenshot = detail.artifacts.find((artifact) => artifact.kind === "screenshot");

  return (
    <main className="page-content">
      <Link href={`/projects/${detail.project_id}`} className="back-link"><ArrowLeft size={14} />Back to project</Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Scan report</span>
          <h1 className="heading-with-badge">{detail.target_url} <RunStatusBadge status={detail.status} /></h1>
          <p className="page-subtitle">
            {detail.status === "queued" && "Waiting for the scan worker. This page updates automatically."}
            {detail.status === "running" && "A headless browser is checking the website. This page updates automatically."}
            {detail.status === "completed" && "The scan finished and every check ran."}
            {detail.status === "completed_with_errors" && "The scan finished, but at least one check could not run."}
            {detail.status === "failed" && (detail.failure_reason ?? "The scan could not be completed.")}
            {detail.status === "cancelled" && "This scan was cancelled before it started."}
          </p>
        </div>
      </div>
      {pollError !== null && !finished && <div className="error-box" role="status">Temporarily unable to refresh this scan; retrying.</div>}
      {gaveUp && !finished && <div className="error-box" role="alert">Automatic updates stopped. <button className="inline-retry" onClick={onRefresh}>Refresh</button></div>}

      <section className="metrics-grid" aria-label="Scan summary">
        <Metric label="Checks passed" value={detail.checks_total ? `${detail.checks_passed}/${detail.checks_total}` : "—"} note={detail.checks_total ? `${detail.checks_failed} with issues · ${detail.checks_errored} could not run · ${detail.checks_skipped} skipped` : "Available when the scan finishes"} />
        <Metric label="Findings" value={finished && detail.checks_total ? String(detail.findings_count) : "—"} note="Distinct issues observed" />
        <Metric label="Started" value={detail.started_at ? formatDateTime(detail.started_at) : "—"} note={`Queued ${formatDateTime(detail.created_at)}`} small />
        <Metric label="Duration" value={formatDuration(detail.duration_ms)} note={detail.finished_at ? `Finished ${formatDateTime(detail.finished_at)}` : "Not finished"} small />
      </section>

      {finished && detail.checks_total > 0 && <SeverityCounts counts={detail.severity_counts} />}

      <div className="detail-grid report-grid">
        <section className="panel" aria-labelledby="checks-title">
          <div className="panel-header"><div><div className="panel-title" id="checks-title">Checks</div><div className="panel-caption">Rule-based browser checks; not an accessibility or SEO audit</div></div></div>
          {detail.checks.length === 0 ? <div className="loading-state">{finished ? "No check results were recorded." : "Results appear when the scan finishes."}</div> : (
            <ul className="check-list">
              {detail.checks.map((check) => (
                <li key={check.id} className="check-item">
                  <div className="check-item-top"><strong>{check.name}</strong><CheckStatusBadge status={check.status} /></div>
                  <p>{check.summary}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="detail-card" aria-labelledby="screenshot-title">
          <h2 id="screenshot-title">Screenshot</h2>
          {screenshot ? (
            <a href={artifactUrl(screenshot)} target="_blank" rel="noreferrer" className="screenshot-link">
              <img src={artifactUrl(screenshot)} alt={`Screenshot of ${detail.final_url ?? detail.target_url}`} width={screenshot.width ?? undefined} height={screenshot.height ?? undefined} className="screenshot" />
            </a>
          ) : <p className="muted-small">{finished ? "No screenshot was captured for this scan." : "Captured after the page loads."}</p>}
          {detail.final_url && detail.final_url !== detail.target_url && <p className="muted-small">Final URL after redirects: {detail.final_url}</p>}
        </section>
      </div>

      {finished && detail.checks_total > 0 && <FindingsSection runId={detail.id} />}
    </main>
  );
}

function Metric({ label, value, note, small }: { label: string; value: string; note: string; small?: boolean }) {
  return (
    <article className="metric-card">
      <div className="metric-top"><span>{label}</span></div>
      <div className={`metric-value${small ? " metric-value-small" : ""}`}>{value}</div>
      <div className="metric-note">{note}</div>
    </article>
  );
}

function FindingsSection({ runId }: { runId: string }) {
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Severity | "all">("all");

  useEffect(() => {
    let active = true;
    Promise.all([scanApi.findings(runId), scanApi.comparison(runId)]).then(([items, compared]) => {
      if (!active) return;
      setFindings(items);
      setComparison(compared);
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof ApiError ? reason.message : "Unable to load findings.");
    });
    return () => { active = false; };
  }, [runId]);

  const visible = useMemo(
    () => (findings ?? []).filter((finding) => filter === "all" || finding.severity === filter),
    [findings, filter],
  );

  return (
    <section className="panel findings-panel" aria-labelledby="findings-title">
      <div className="panel-header">
        <div><div className="panel-title" id="findings-title">Findings</div><div className="panel-caption">{comparison ? <ComparisonText comparison={comparison} /> : "Issues observed during this scan"}</div></div>
      </div>
      <div className="filter-bar" role="group" aria-label="Filter by severity">
        {(["all", ...SEVERITIES] as const).map((value) => (
          <button key={value} type="button" className={`filter-chip${filter === value ? " active" : ""}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>
            {value === "all" ? "All" : value}
          </button>
        ))}
      </div>
      {error ? <div className="error-box panel-error" role="alert">{error}</div>
        : findings === null ? <div className="loading-state" role="status">Loading findings…</div>
          : visible.length === 0 ? <div className="loading-state">{findings.length === 0 ? "No issues were found by these checks." : "No findings with this severity."}</div>
            : (
              <ul className="finding-list">
                {visible.map((finding) => (
                  <li key={finding.id} className="finding-item">
                    <div className="finding-badges"><SeverityBadge severity={finding.severity} /><ConfidenceBadge confidence={finding.confidence} />{finding.http_status && <span className="badge">HTTP {finding.http_status}</span>}</div>
                    <Link href={`/findings/${finding.id}`} className="finding-title">{finding.title}</Link>
                    <p className="finding-description">{finding.description}</p>
                    {finding.affected_url && <p className="finding-url">{finding.affected_url}</p>}
                  </li>
                ))}
              </ul>
            )}
    </section>
  );
}

function ComparisonText({ comparison }: { comparison: RunComparison }) {
  if (!comparison.previous_run_id) return <>First finished scan of this project; nothing to compare yet.</>;
  return (
    <>
      Compared with the <Link className="text-link" href={`/scans/${comparison.previous_run_id}`}>previous scan</Link>:{" "}
      {comparison.new.length} new, {comparison.resolved.length} no longer seen, {comparison.unchanged_count} unchanged.
    </>
  );
}
