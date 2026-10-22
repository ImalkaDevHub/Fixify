"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Bug, CheckCircle2, FolderKanban, Plus, ScanSearch } from "lucide-react";
import { ApiError, projectApi, scanApi, type DashboardSummary, type Project } from "@/lib/api";
import { ProjectList } from "@/components/projects/project-list";

export function DashboardContent() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([projectApi.list(5), scanApi.summary()]).then(([items, totals]) => {
      if (!active) return;
      setProjects(items);
      setSummary(totals);
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof ApiError ? reason.message : "Unable to load projects right now.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const show = (value: number | undefined) => (loading || error || value === undefined ? "—" : value);
  const metrics = [
    { label: "Total projects", value: show(summary?.project_count), note: "Websites in your workspace", icon: FolderKanban },
    { label: "Scans run", value: show(summary?.scan_count), note: summary?.active_scan_count ? `${summary.active_scan_count} queued or running` : "All scans, any outcome", icon: ScanSearch },
    { label: "Open findings", value: show(summary?.latest_findings_count), note: "From each project's latest finished scan", icon: Bug },
    { label: "Fixes verified", value: "—", note: "Coming with review workflows", icon: CheckCircle2 },
  ];

  return (
    <main className="page-content">
      <div className="page-heading">
        <div><span className="eyebrow">Workspace overview</span><h1>Good to have you here</h1>
          <p className="page-subtitle">A clear view of the websites you’re preparing to test.</p>
        </div>
        <Link href="/projects/new" className="button"><Plus size={16} />New project</Link>
      </div>

      <section className="welcome-card" aria-labelledby="welcome-title">
        <div className="welcome-copy">
          <h2 id="welcome-title">Set up your first website</h2>
          <p>Add a website you are authorized to test, then run a scan. A headless browser records real console errors, failed requests, HTTP errors, broken links, and a screenshot.</p>
        </div>
        <div className="welcome-steps" aria-label="Getting started">
          <span className="welcome-step"><span className="step-number">1</span>Add project</span>
          <span className="welcome-step"><span className="step-number">2</span>Run a scan</span>
        </div>
      </section>

      <section className="metrics-grid" aria-label="Workspace metrics">
        {metrics.map(({ label, value, note, icon: Icon }) => (
          <article className="metric-card" key={label}>
            <div className="metric-top"><span>{label}</span><span className="metric-icon"><Icon size={15} /></span></div>
            <div className="metric-value">{value}</div><div className="metric-note">{note}</div>
          </article>
        ))}
      </section>

      <section className="panel" aria-labelledby="recent-projects-title">
        <div className="panel-header">
          <div><div className="panel-title" id="recent-projects-title">Recent projects</div><div className="panel-caption">Your latest websites added to Fixify</div></div>
          <Link href="/projects" className="text-link">View all <ArrowRight size={14} /></Link>
        </div>
        {error ? <div className="error-box" role="alert">{error} <button className="inline-retry" onClick={() => window.location.reload()}>Try again</button></div>
          : loading ? <div className="loading-state" role="status">Loading your projects…</div>
            : <ProjectList projects={projects} />}
      </section>
    </main>
  );
}
