"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, artifactUrl, scanApi, type FindingDetail as FindingDetailData } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { ConfidenceBadge, SeverityBadge } from "@/components/scans/badges";

const CHECK_LABELS: Record<string, string> = {
  page_navigation: "Page navigation",
  console_errors: "JavaScript console errors",
  uncaught_exceptions: "Uncaught JavaScript exceptions",
  failed_requests: "Failed network requests",
  http_errors: "HTTP error responses",
  broken_links: "Broken links",
  page_basics: "Basic page checks",
  screenshot: "Screenshot",
};

export function FindingDetail({ findingId }: { findingId: string }) {
  const [finding, setFinding] = useState<FindingDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    scanApi.finding(findingId).then((item) => {
      if (active) setFinding(item);
    }).catch((reason: unknown) => {
      if (!active) return;
      const notFound = reason instanceof ApiError && (reason.status === 404 || reason.status === 422);
      setError(notFound ? "This finding could not be found." : reason instanceof ApiError ? reason.message : "Unable to load this finding.");
    });
    return () => { active = false; };
  }, [findingId]);

  if (error) return <main className="page-content"><Link href="/projects" className="back-link"><ArrowLeft size={14} />Back to projects</Link><div className="error-box" role="alert">{error}</div></main>;
  if (!finding) return <main className="page-content"><div className="loading-state" role="status">Loading finding…</div></main>;

  return (
    <main className="page-content">
      <Link href={`/scans/${finding.test_run_id}`} className="back-link"><ArrowLeft size={14} />Back to scan report</Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Finding</span>
          <h1>{finding.title}</h1>
          <div className="finding-badges heading-badges"><SeverityBadge severity={finding.severity} /><ConfidenceBadge confidence={finding.confidence} /></div>
        </div>
      </div>
      <div className="detail-grid">
        <section className="detail-card">
          <h2>What was observed</h2>
          <p className="finding-description">{finding.description}</p>
          {finding.confidence === "suspected" && <p className="muted-small">Suspected: the scanner saw this once, but it may be temporary or caused by the site limiting automated visitors. Re-scan before treating it as a bug.</p>}
          <div className="detail-row"><span className="detail-label">Check</span><span className="detail-value">{CHECK_LABELS[finding.check_type] ?? finding.check_type}</span></div>
          <div className="detail-row"><span className="detail-label">Type</span><span className="detail-value">{finding.finding_type}</span></div>
          <div className="detail-row"><span className="detail-label">Affected URL</span><span className="detail-value">{finding.affected_url ?? "—"}</span></div>
          <div className="detail-row"><span className="detail-label">HTTP status</span><span className="detail-value">{finding.http_status ?? "—"}</span></div>
          <div className="detail-row"><span className="detail-label">Recorded</span><span className="detail-value">{formatDateTime(finding.created_at)}</span></div>
          <div className="detail-row"><span className="detail-label">First seen in this project</span><span className="detail-value">{formatDateTime(finding.first_detected_at)}</span></div>
        </section>
        <section className="detail-card">
          <h2>Evidence</h2>
          <p className="muted-small">Sanitized and size-limited. Website content is shown as plain text and never executed.</p>
          <pre className="evidence">{JSON.stringify(finding.evidence, null, 2)}</pre>
          {finding.artifact && (
            // The image is served by the API with a restrictive Content-Security-Policy.
            <img src={artifactUrl(finding.artifact)} alt="Screenshot captured during the scan" className="screenshot" />
          )}
        </section>
      </div>
    </main>
  );
}
