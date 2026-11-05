"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Clock, GitPullRequest, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { analyticsApi, projectApi } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { formatDuration, timeAgo } from "@/lib/utils";
import { ChartEmpty, HealthTrendChart, NewResolvedChart, ScanActivityChart, SeverityDonut, SeverityOverTimeChart } from "@/components/charts";
import { RunStatusBadge } from "@/components/status";
import { Alert, Card, CardHeader, PageHeader, Reveal, Segmented, Select, Skeleton, StatCard } from "@/components/ui/primitives";

export function AnalyticsPage() {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const [projectId, setProjectId] = useState("");
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => projectApi.list() });
  const analytics = useQuery({ queryKey: ["analytics", days, projectId], queryFn: () => analyticsApi.overview(Number(days), projectId || undefined) });
  const data = analytics.data;
  const hasData = !!data && data.daily.length > 0;
  const total = data ? Object.values(data.current_findings).reduce((a, b) => a + b, 0) : 0;

  return (
    <>
      <PageHeader
        eyebrow="Insights"
        title="Analytics"
        description="Computed from your persisted scans only. Empty means nothing has been scanned in this period."
        actions={
          <>
            <Select aria-label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 w-48">
              <option value="">All projects</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Segmented label="analytics-range" value={days} onChange={setDays} options={[{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }]} />
          </>
        }
      />
      {analytics.error && <Alert tone="error">{errorText(analytics.error)}</Alert>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {!data ? (
          Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-[112px] rounded-[14px]" />)
        ) : (
          <>
            <StatCard label="Scans" value={data.scan_count} hint={`${data.failed_scan_count} failed`} icon={<Activity className="h-4 w-4" />} />
            <StatCard label="Avg. duration" value={formatDuration(data.average_duration_ms)} icon={<Clock className="h-4 w-4" />} tone="cyan" />
            <StatCard label="Critical now" value={data.current_findings.critical} hint={`${total} findings in total`} icon={<ShieldAlert className="h-4 w-4" />} tone="critical" />
            <StatCard label="Resolved" value={data.resolved_findings} hint={`${data.new_findings} new`} icon={<CheckCircle2 className="h-4 w-4" />} tone="success" />
            <StatCard label="Fixes to review" value={data.open_fix_proposals} icon={<Sparkles className="h-4 w-4" />} tone="warning" />
            <StatCard label="Open PRs" value={data.open_pull_requests} icon={<GitPullRequest className="h-4 w-4" />} />
          </>
        )}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {[
          { title: "Findings over time", description: "Severity of findings in each day's finished scans", chart: hasData ? <SeverityOverTimeChart data={data!.daily} /> : null },
          { title: "New vs resolved", description: "Compared with each project's previous finished scan", chart: hasData ? <NewResolvedChart data={data!.daily} /> : null },
          { title: "Scan history", description: "Scans started per day", chart: hasData ? <ScanActivityChart data={data!.daily} /> : null },
          { title: "Project health trend", description: data?.health_formula, chart: hasData ? <HealthTrendChart data={data!.daily} /> : null },
        ].map((item, index) => (
          <Reveal key={item.title} delay={index * 0.05}>
            <Card>
              <CardHeader title={item.title} description={item.description} />
              <div className="p-4">{item.chart ?? <ChartEmpty>{data ? "No scans in this period." : "Loading…"}</ChartEmpty>}</div>
            </Card>
          </Reveal>
        ))}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card>
          <CardHeader title="Findings by severity" description="Latest finished scan of each project" />
          <div className="p-4">{data && total ? <SeverityDonut counts={data.current_findings} /> : <ChartEmpty>No open findings.</ChartEmpty>}</div>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Recent scans in this period" />
          {!data?.recent_scans.length ? (
            <p className="px-5 py-6 text-[13px] text-muted">No scans.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-[13px]">
                <thead className="text-[11px] uppercase tracking-wider text-subtle"><tr><th className="px-5 py-2.5 font-medium">Project</th><th className="font-medium">Status</th><th className="font-medium">Findings</th><th className="font-medium">Duration</th><th className="px-5 font-medium">When</th></tr></thead>
                <tbody className="divide-y divide-line-soft">
                  {data.recent_scans.map((scan) => (
                    <tr key={scan.id} className="hover:bg-elevated/40">
                      <td className="px-5 py-2.5"><Link href={`/scans/${scan.id}`} className="hover:text-violet-soft">{scan.project_name}</Link></td>
                      <td><RunStatusBadge status={scan.status} /></td>
                      <td className="tabular-nums">{scan.findings}{scan.critical ? <span className="ml-1 text-critical">({scan.critical} critical)</span> : null}</td>
                      <td className="tabular-nums text-muted">{formatDuration(scan.duration_ms)}</td>
                      <td className="px-5 text-muted">{timeAgo(scan.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
