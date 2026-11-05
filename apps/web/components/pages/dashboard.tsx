"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowRight, Bug, CheckCircle2, FolderKanban, FolderPlus, GitBranch, Radar, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { analyticsApi, findingApi, projectApi, scanApi } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { hostname, timeAgo } from "@/lib/utils";
import { ChartEmpty, ScanActivityChart, SeverityDonut } from "@/components/charts";
import { RunStatusBadge, SeverityBadge, SeverityBar } from "@/components/status";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardHeader, EmptyState, PageHeader, Reveal, Skeleton, SkeletonRows, StatCard } from "@/components/ui/primitives";

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

export function DashboardPage() {
  const { data: me } = useMe();
  const analytics = useQuery({ queryKey: ["analytics", 30], queryFn: () => analyticsApi.overview(30), refetchInterval: 30_000 });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => projectApi.list() });
  const scans = useQuery({ queryKey: ["scans", "recent"], queryFn: () => scanApi.recent(6), refetchInterval: (q) => (q.state.data?.some((s) => s.status === "queued" || s.status === "running") ? 4000 : 30_000) });
  const findings = useQuery({ queryKey: ["findings", "latest"], queryFn: () => findingApi.list() });
  const names = new Map(projects.data?.map((p) => [p.id, p.name]));
  const data = analytics.data;
  const current = data ? Object.values(data.current_findings).reduce((a, b) => a + b, 0) : 0;

  if (projects.data && projects.data.length === 0) {
    return (
      <>
        <PageHeader eyebrow="Overview" title={`${greeting()}${me ? `, ${me.display_name.split(" ")[0]}` : ""}`} description="Let's run your first real-browser scan." />
        <Reveal>
          <Card className="overflow-hidden">
            <div className="grid gap-0 md:grid-cols-3">
              {[
                { icon: FolderPlus, title: "1. Add a website", text: "Create a project with the URL you are authorized to test." },
                { icon: Radar, title: "2. Run a scan", text: "Headless Chromium records console errors, broken requests, links, and more." },
                { icon: Sparkles, title: "3. Review fixes", text: "Get AI explanations and pull requests that you approve first." },
              ].map(({ icon: Icon, title, text }) => (
                <div key={title} className="border-b border-line-soft p-6 md:border-b-0 md:border-r last:border-0">
                  <Icon className="h-5 w-5 text-violet-soft" />
                  <h3 className="mt-3 text-[14px] font-semibold">{title}</h3>
                  <p className="mt-1 text-[13px] text-muted">{text}</p>
                </div>
              ))}
            </div>
            <div className="flex justify-end border-t border-line-soft bg-panel/50 px-6 py-4">
              <ButtonLink href="/projects/new">Create your first project <ArrowRight className="h-4 w-4" /></ButtonLink>
            </div>
          </Card>
        </Reveal>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title={`${greeting()}${me ? `, ${me.display_name.split(" ")[0]}` : ""}`}
        description="What your scans found across all projects in the last 30 days."
        actions={
          <>
            <ButtonLink href="/projects" variant="secondary"><Radar className="h-4 w-4" /> Run a scan</ButtonLink>
            <ButtonLink href="/projects/new"><FolderPlus className="h-4 w-4" /> New project</ButtonLink>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {analytics.isLoading || !data ? (
          Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-[112px] rounded-[14px]" />)
        ) : (
          <>
            <StatCard label="Projects" value={data.project_count} icon={<FolderKanban className="h-4 w-4" />} />
            <StatCard label="Scans (30 days)" value={data.scan_count} hint={data.active_scan_count ? `${data.active_scan_count} in progress` : `${data.failed_scan_count} failed`} icon={<Activity className="h-4 w-4" />} tone="cyan" />
            <StatCard label="Current findings" value={current} hint="Latest scan of each project" icon={<Bug className="h-4 w-4" />} tone="warning" />
            <StatCard label="Critical issues" value={data.current_findings.critical} hint={`${data.current_findings.high} high severity`} icon={<ShieldAlert className="h-4 w-4" />} tone="critical" />
            <StatCard label="Resolved (30 days)" value={data.resolved_findings} hint={`${data.new_findings} new`} icon={<CheckCircle2 className="h-4 w-4" />} tone="success" />
          </>
        )}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Reveal className="lg:col-span-2" delay={0.05}>
          <Card>
            <CardHeader title="Scan activity" description="Scans per day, including failures" />
            <div className="p-4">
              {data && data.daily.length ? <ScanActivityChart data={data.daily} /> : <ChartEmpty>No scans in the last 30 days.</ChartEmpty>}
            </div>
          </Card>
        </Reveal>
        <Reveal delay={0.1}>
          <Card className="h-full">
            <CardHeader title="Severity distribution" description="Across each project's latest scan" />
            <div className="p-4">
              {data && current ? <SeverityDonut counts={data.current_findings} /> : <ChartEmpty>{data ? "No open findings. Nice." : "Loading…"}</ChartEmpty>}
            </div>
          </Card>
        </Reveal>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Reveal className="lg:col-span-2" delay={0.12}>
          <Card>
            <CardHeader title="Recent scans" action={<Link href="/scans" className="text-[12.5px] text-violet-soft hover:text-ink">View all</Link>} />
            {scans.isLoading ? (
              <SkeletonRows />
            ) : !scans.data?.length ? (
              <EmptyState icon={<Radar className="h-5 w-5" />} title="No scans yet" description="Open a project and press Run scan." action={<ButtonLink href="/projects" variant="secondary">Open projects</ButtonLink>} />
            ) : (
              <ul className="divide-y divide-line-soft">
                {scans.data.map((scan) => (
                  <li key={scan.id}>
                    <Link href={`/scans/${scan.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 transition-colors hover:bg-elevated/40">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13.5px] font-medium">{names.get(scan.project_id) ?? "Project"}</p>
                        <p className="truncate text-[12px] text-muted">{hostname(scan.target_url)} · {timeAgo(scan.created_at)}{scan.trigger === "scheduled" ? " · scheduled" : ""}</p>
                      </div>
                      <div className="hidden w-40 sm:block"><SeverityBar counts={scan.severity_counts} /></div>
                      <span className="w-16 text-right text-[12.5px] tabular-nums text-muted">{scan.findings_count} found</span>
                      <RunStatusBadge status={scan.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </Reveal>
        <Reveal delay={0.16}>
          <Card className="h-full">
            <CardHeader title="Project health" description="100 minus weighted findings of the latest scan" />
            <ul className="divide-y divide-line-soft">
              {data?.projects.slice(0, 6).map((project) => (
                <li key={project.project_id}>
                  <Link href={`/projects/${project.project_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-elevated/40">
                    <span className="min-w-0 flex-1 truncate text-[13px]">{project.name}</span>
                    {project.health === null ? (
                      <span className="text-[12px] text-subtle">Not scanned</span>
                    ) : (
                      <>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-elevated">
                          <div className="h-full rounded-full bg-gradient-to-r from-violet to-cyan" style={{ width: `${project.health}%` }} />
                        </div>
                        <span className="w-8 text-right text-[12.5px] font-semibold tabular-nums">{project.health}</span>
                      </>
                    )}
                  </Link>
                </li>
              ))}
              {!data && <SkeletonRows rows={3} />}
            </ul>
          </Card>
        </Reveal>
      </div>

      <Reveal delay={0.2} className="mt-5">
        <Card>
          <CardHeader title="Recent findings" description="Most severe first, from each project's latest scan" action={<Link href="/findings" className="text-[12.5px] text-violet-soft hover:text-ink">All findings</Link>} />
          {findings.isLoading ? (
            <SkeletonRows />
          ) : !findings.data?.length ? (
            <EmptyState icon={<CheckCircle2 className="h-5 w-5" />} title="No findings" description="Your latest scans found no issues." />
          ) : (
            <ul className="divide-y divide-line-soft">
              {findings.data.slice(0, 6).map((finding) => (
                <li key={finding.id}>
                  <Link href={`/findings/${finding.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-elevated/40">
                    <SeverityBadge severity={finding.severity} />
                    <span className="min-w-0 flex-1 truncate text-[13px]">{finding.title}</span>
                    <span className="hidden truncate text-[12px] text-muted md:block">{names.get(finding.project_id)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </Reveal>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {[
          { href: "/fixes", icon: Sparkles, title: "Review AI fixes", text: `${data?.open_fix_proposals ?? 0} waiting for review` },
          { href: "/github", icon: GitBranch, title: "GitHub", text: `${data?.open_pull_requests ?? 0} open pull requests` },
          { href: "/analytics", icon: Activity, title: "Analytics", text: "Trends, health, new vs resolved" },
        ].map(({ href, icon: Icon, title, text }) => (
          <Link key={href} href={href}>
            <Card hover className="flex items-center gap-3 p-4">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-violet/20 bg-violet/10 text-violet-soft"><Icon className="h-4 w-4" /></span>
              <span className="min-w-0">
                <span className="block text-[13.5px] font-medium">{title}</span>
                <span className="block text-[12px] text-muted">{text}</span>
              </span>
              <ArrowRight className="ml-auto h-4 w-4 text-subtle" />
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
