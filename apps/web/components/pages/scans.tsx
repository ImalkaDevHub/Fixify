"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, Camera, CheckCircle2, ExternalLink, Minus, Radar, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { projectApi, scanApi, SEVERITIES, TERMINAL_STATUSES, type CheckResult, type Severity } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { cn, formatDateTime, formatDuration, hostname, timeAgo } from "@/lib/utils";
import { ConfidenceBadge, RunStatusBadge, SeverityBadge, SeverityBar, SeverityCounts } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, KeyValue, PageHeader, Reveal, Segmented, SkeletonRows } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

export function ScansPage() {
  const scans = useQuery({
    queryKey: ["scans", "all"],
    queryFn: () => scanApi.recent(100),
    refetchInterval: (q) => (q.state.data?.some((s) => !TERMINAL_STATUSES.has(s.status)) ? 4000 : 30_000),
  });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => projectApi.list() });
  const names = new Map(projects.data?.map((p) => [p.id, p.name]));
  return (
    <>
      <PageHeader eyebrow="Monitor" title="Scans" description="Every scan across your projects, newest first. Active scans update live." />
      <Card>
        {scans.isLoading ? (
          <SkeletonRows rows={6} />
        ) : scans.error ? (
          <div className="p-5"><Alert tone="error">{errorText(scans.error)}</Alert></div>
        ) : !scans.data?.length ? (
          <EmptyState icon={<Radar className="h-5 w-5" />} title="No scans yet" description="Open a project and run your first scan." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[13px]">
              <thead className="border-b border-line-soft text-[11px] uppercase tracking-wider text-subtle">
                <tr><th className="px-5 py-3 font-medium">Project</th><th className="font-medium">Status</th><th className="font-medium">Findings</th><th className="font-medium">Checks</th><th className="font-medium">Duration</th><th className="px-5 font-medium">Started</th></tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {scans.data.map((scan) => (
                  <tr key={scan.id} className="transition-colors hover:bg-elevated/40">
                    <td className="px-5 py-3">
                      <Link href={`/scans/${scan.id}`} className="font-medium hover:text-violet-soft">{names.get(scan.project_id) ?? "Project"}</Link>
                      <p className="text-[12px] text-muted">{hostname(scan.target_url)}{scan.trigger === "scheduled" ? " · scheduled" : ""}</p>
                    </td>
                    <td><RunStatusBadge status={scan.status} /></td>
                    <td><div className="flex items-center gap-2"><span className="w-6 tabular-nums">{scan.findings_count}</span><SeverityBar counts={scan.severity_counts} className="w-24" /></div></td>
                    <td className="tabular-nums text-muted">{scan.checks_total ? `${scan.checks_passed}/${scan.checks_total}` : "—"}</td>
                    <td className="tabular-nums text-muted">{formatDuration(scan.duration_ms)}</td>
                    <td className="px-5 text-muted">{timeAgo(scan.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

const CHECK_ICON = { passed: CheckCircle2, failed: XCircle, error: XCircle, skipped: Minus };
const CHECK_TONE = { passed: "text-success", failed: "text-critical", error: "text-warning", skipped: "text-subtle" };

function CheckRow({ check }: { check: CheckResult }) {
  const [open, setOpen] = useState(false);
  const Icon = CHECK_ICON[check.status];
  return (
    <li>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-start gap-3 px-5 py-3 text-left transition-colors hover:bg-elevated/40">
        <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", CHECK_TONE[check.status])} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium">{check.name}</span>
          <span className="block text-[12px] text-muted">{check.summary}</span>
        </span>
        <span className="shrink-0 text-[11.5px] tabular-nums text-subtle">{formatDuration(check.duration_ms)}</span>
      </button>
      {open && Object.keys(check.details).length > 0 && (
        <pre className="code-font mx-5 mb-3 max-h-64 overflow-auto rounded-lg border border-line-soft bg-panel p-3 text-[11.5px] text-ink/80 scrollbar-thin">{JSON.stringify(check.details, null, 2)}</pre>
      )}
    </li>
  );
}

export function ScanDetailPage({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const scan = useQuery({ queryKey: ["scan", id], queryFn: () => scanApi.get(id), refetchInterval: (q) => (q.state.data && !TERMINAL_STATUSES.has(q.state.data.status) ? 3000 : false) });
  const done = !!scan.data && TERMINAL_STATUSES.has(scan.data.status);
  const findings = useQuery({ queryKey: ["scan-findings", id], queryFn: () => scanApi.findings(id), enabled: done });
  const comparison = useQuery({ queryKey: ["scan-comparison", id], queryFn: () => scanApi.comparison(id), enabled: done });
  const project = useQuery({ queryKey: ["project", scan.data?.project_id], queryFn: () => projectApi.get(scan.data!.project_id), enabled: !!scan.data });
  const cancel = useMutation({ mutationFn: () => scanApi.cancel(id), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["scan", id] }); toast.success("Scan cancelled."); }, onError: (e) => toast.error(errorText(e)) });

  if (scan.isLoading) return <SkeletonRows rows={6} />;
  if (!scan.data) return <Alert tone="error" title="Scan not available">{errorText(scan.error, "Not found.")}</Alert>;
  const s = scan.data;
  const screenshot = s.artifacts.find((a) => a.kind === "screenshot");
  const visible = (findings.data ?? []).filter((f) => severity === "all" || f.severity === severity);

  return (
    <>
      <PageHeader
        eyebrow={project.data ? project.data.name : "Scan report"}
        title={<span className="flex flex-wrap items-center gap-3">Scan report <RunStatusBadge status={s.status} /></span>}
        description={<span className="break-all">{s.final_url ?? s.target_url} · {formatDateTime(s.created_at)}{s.trigger === "scheduled" ? " · scheduled" : ""}</span>}
        actions={
          <>
            {s.status === "queued" && <Button variant="danger" size="sm" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel scan</Button>}
            {project.data && <Link href={`/projects/${project.data.id}`} className="text-[13px] text-violet-soft hover:text-ink">Back to project</Link>}
          </>
        }
      />
      {!done && <Alert tone="info" title={s.status === "queued" ? "Waiting for a scanner" : "Scanning now"} className="mb-5">This page refreshes automatically.</Alert>}
      {s.failure_reason && <Alert tone={s.status === "failed" ? "error" : "warning"} title={s.status === "failed" ? "The scan failed" : "Note"} className="mb-5">{s.failure_reason}</Alert>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Findings", s.findings_count],
          ["Checks passed", s.checks_total ? `${s.checks_passed} / ${s.checks_total}` : "—"],
          ["Duration", formatDuration(s.duration_ms)],
          ["Links checked", `≤ ${s.max_links}`],
        ].map(([label, value]) => (
          <Card key={label as string} className="p-4">
            <p className="text-[12px] text-muted">{label}</p>
            <p className="mt-1.5 text-[22px] font-semibold tabular-nums">{value}</p>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader title="Findings" description="Grouped by severity. Suspected issues are labelled and never shown as confirmed." />
            <div className="border-b border-line-soft px-5 py-3">
              <SeverityCounts counts={s.severity_counts} />
              <div className="mt-3">
                <Segmented label="severity-filter" value={severity} onChange={setSeverity} options={[{ value: "all", label: "All" }, ...SEVERITIES.map((v) => ({ value: v, label: <span className="capitalize">{v}</span> }))]} />
              </div>
            </div>
            {!done || findings.isLoading ? (
              <SkeletonRows />
            ) : !visible.length ? (
              <EmptyState icon={<CheckCircle2 className="h-5 w-5" />} title={findings.data?.length ? "Nothing at this severity" : "No findings"} description={findings.data?.length ? "Choose another filter." : "Every check passed without issues."} />
            ) : (
              <ul className="divide-y divide-line-soft">
                {visible.map((finding, index) => (
                  <Reveal key={finding.id} delay={Math.min(index * 0.025, 0.25)}>
                    <Link href={`/findings/${finding.id}`} className="block px-5 py-3.5 transition-colors hover:bg-elevated/40">
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityBadge severity={finding.severity} />
                        <ConfidenceBadge value={finding.confidence} />
                        {finding.http_status && <Badge>HTTP {finding.http_status}</Badge>}
                      </div>
                      <p className="mt-1.5 text-[13.5px] font-medium">{finding.title}</p>
                      {finding.affected_url && <p className="truncate text-[12px] text-muted">{finding.affected_url}</p>}
                    </Link>
                  </Reveal>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Checks" description="Click a check to see its recorded details." />
            {s.checks.length ? <ul className="divide-y divide-line-soft">{s.checks.map((check) => <CheckRow key={check.id} check={check} />)}</ul> : <p className="px-5 py-6 text-[13px] text-muted">No checks have run yet.</p>}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Compared with previous scan" />
            <div className="p-5">
              {!comparison.data ? (
                <p className="text-[13px] text-muted">{done ? "Loading…" : "Available when the scan finishes."}</p>
              ) : !comparison.data.previous_run_id ? (
                <p className="text-[13px] text-muted">This is the first finished scan of the project.</p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-lg border border-critical/25 bg-critical/[0.06] p-3"><ArrowUpRight className="mx-auto h-4 w-4 text-critical" /><p className="mt-1 text-[20px] font-semibold">{comparison.data.new.length}</p><p className="text-[11px] text-muted">New</p></div>
                    <div className="rounded-lg border border-success/25 bg-success/[0.06] p-3"><ArrowDownRight className="mx-auto h-4 w-4 text-success" /><p className="mt-1 text-[20px] font-semibold">{comparison.data.resolved.length}</p><p className="text-[11px] text-muted">Resolved</p></div>
                    <div className="rounded-lg border border-line bg-panel p-3"><Minus className="mx-auto h-4 w-4 text-subtle" /><p className="mt-1 text-[20px] font-semibold">{comparison.data.unchanged_count}</p><p className="text-[11px] text-muted">Unchanged</p></div>
                  </div>
                  {[...comparison.data.new.map((f) => ({ ...f, kind: "new" })), ...comparison.data.resolved.map((f) => ({ ...f, kind: "resolved" }))].slice(0, 8).map((f) => (
                    <Link key={f.kind + f.fingerprint} href={`/findings/${f.finding_id}`} className="mt-2 flex items-center gap-2 text-[12.5px] hover:text-violet-soft">
                      <span className={f.kind === "new" ? "text-critical" : "text-success"}>{f.kind === "new" ? "+" : "−"}</span>
                      <span className="truncate">{f.title}</span>
                    </Link>
                  ))}
                  <Link href={`/scans/${comparison.data.previous_run_id}`} className="mt-3 block text-[12.5px] text-violet-soft hover:text-ink">Open previous scan →</Link>
                </>
              )}
            </div>
          </Card>
          <Card>
            <CardHeader title={<span className="flex items-center gap-2"><Camera className="h-4 w-4" /> Screenshot</span>} />
            <div className="p-4">
              {screenshot ? (
                <a href={screenshot.url} target="_blank" rel="noreferrer">
                  {/* Plain <img>: served by the API with auth cookies */}
                  <img src={screenshot.url} alt={`Screenshot of ${hostname(s.final_url ?? s.target_url)}`} className="w-full rounded-lg border border-line" loading="lazy" />
                </a>
              ) : (
                <p className="text-[13px] text-muted">{done ? "No screenshot (capture failed or removed by retention)." : "Captured during the scan."}</p>
              )}
            </div>
          </Card>
          <Card>
            <CardHeader title="Details" />
            <div className="px-5 py-2">
              <KeyValue items={[
                { label: "Target", value: <a href={s.target_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 hover:text-violet-soft">{hostname(s.target_url)} <ExternalLink className="h-3 w-3" /></a> },
                { label: "Started", value: formatDateTime(s.started_at) },
                { label: "Finished", value: formatDateTime(s.finished_at) },
                { label: "Attempts", value: s.attempts },
                { label: "Browser", value: "Headless Chromium (Playwright)" },
              ]} />
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
