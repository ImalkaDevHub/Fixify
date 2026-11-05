"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Bug, CheckCircle2, FileCode2, FolderGit2, Lightbulb, Loader2, Sparkles, Users, Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ACTIVE_JOB, findingApi, fixApi, jobApi, projectApi, SEVERITIES, type Analysis, type Job, type Severity } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { formatDateTime, humanize, timeAgo } from "@/lib/utils";
import { ConfidenceBadge, FixStatusBadge, JobStatusBadge, SeverityBadge, ValidationBadge } from "@/components/status";
import { Button, ButtonLink } from "@/components/ui/button";
import { Dialog } from "@/components/ui/overlays";
import { Alert, Badge, Card, CardHeader, EmptyState, Input, KeyValue, Label, PageHeader, Reveal, Segmented, SkeletonRows, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

export function FindingsPage() {
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [latestOnly, setLatestOnly] = useState(true);
  const findings = useQuery({ queryKey: ["findings", severity, latestOnly], queryFn: () => findingApi.list({ severity: severity === "all" ? undefined : severity, latestOnly }) });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => projectApi.list() });
  const names = new Map(projects.data?.map((p) => [p.id, p.name]));
  return (
    <>
      <PageHeader eyebrow="Monitor" title="Findings" description="Issues recorded by the browser scanner, most severe first." />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Segmented label="finding-severity" value={severity} onChange={setSeverity} options={[{ value: "all", label: "All" }, ...SEVERITIES.map((v) => ({ value: v, label: <span className="capitalize">{v}</span> }))]} />
        <Segmented label="finding-scope" value={latestOnly ? "latest" : "all"} onChange={(v) => setLatestOnly(v === "latest")} options={[{ value: "latest", label: "Latest scans" }, { value: "all", label: "All history" }]} />
      </div>
      <Card>
        {findings.isLoading ? (
          <SkeletonRows rows={6} />
        ) : findings.error ? (
          <div className="p-5"><Alert tone="error">{errorText(findings.error)}</Alert></div>
        ) : !findings.data?.length ? (
          <EmptyState icon={<CheckCircle2 className="h-5 w-5" />} title="No findings" description={severity === "all" ? "Your latest scans found no issues, or nothing has been scanned yet." : "Nothing at this severity."} />
        ) : (
          <ul className="divide-y divide-line-soft">
            {findings.data.map((finding) => (
              <li key={finding.id}>
                <Link href={`/findings/${finding.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-5 py-3.5 transition-colors hover:bg-elevated/40">
                  <SeverityBadge severity={finding.severity} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px] font-medium">{finding.title}</span>
                    <span className="block truncate text-[12px] text-muted">{names.get(finding.project_id)} · {humanize(finding.finding_type)}{finding.affected_url ? ` · ${finding.affected_url}` : ""}</span>
                  </span>
                  <ConfidenceBadge value={finding.confidence} />
                  <span className="text-[12px] text-subtle">since {timeAgo(finding.first_detected_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function AnalysisSection({ icon: Icon, title, children }: { icon: typeof Brain; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line-soft bg-panel/60 p-4">
      <p className="mb-1.5 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-violet-soft"><Icon className="h-3.5 w-3.5" />{title}</p>
      <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink/85">{children}</div>
    </div>
  );
}

function JobProgress({ job, label }: { job: Job; label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-violet/25 bg-violet/[0.06] p-4" role="status" aria-live="polite">
      <Loader2 className="h-4 w-4 animate-spin text-violet-soft" />
      <div className="min-w-0 flex-1 text-[13px]">
        <p className="font-medium">{label}</p>
        <p className="text-muted">{job.status === "queued" ? (job.attempts ? `Retrying (attempt ${job.attempts + 1} of ${job.max_attempts})…` : "Waiting for the worker…") : "Working…"}{job.error ? ` Last error: ${job.error}` : ""}</p>
      </div>
      <JobStatusBadge status={job.status} />
    </div>
  );
}

function AnalysisView({ analysis }: { analysis: Analysis }) {
  return (
    <div className="space-y-3">
      <p className="text-[14px] leading-relaxed">{analysis.summary}</p>
      <div className="flex flex-wrap gap-2">
        <ConfidenceBadge value={analysis.confidence} />
        <Badge tone="cyan">Fix complexity: {analysis.fix_complexity}</Badge>
        <Badge>{analysis.model}</Badge>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <AnalysisSection icon={Brain} title="Technical explanation">{analysis.technical_explanation}</AnalysisSection>
        <AnalysisSection icon={Bug} title="Likely root cause">{analysis.root_cause}</AnalysisSection>
        <AnalysisSection icon={Users} title="User impact">{analysis.user_impact}</AnalysisSection>
        <AnalysisSection icon={Lightbulb} title="Why it matters">{analysis.why_it_matters}</AnalysisSection>
      </div>
      <AnalysisSection icon={Wrench} title="Recommended solution">{analysis.recommended_solution}</AnalysisSection>
      {analysis.suggested_locations.length > 0 && (
        <div className="rounded-xl border border-line-soft bg-panel/60 p-4">
          <p className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-violet-soft"><FileCode2 className="h-3.5 w-3.5" />Related code</p>
          <ul className="space-y-1.5 text-[13px]">
            {analysis.suggested_locations.map((loc) => <li key={loc.path}><span className="font-mono text-cyan">{loc.path}</span> <span className="text-muted">— {loc.reason}</span></li>)}
          </ul>
        </div>
      )}
      {analysis.related_finding_ids.length > 0 && (
        <p className="text-[12.5px] text-muted">Related findings: {analysis.related_finding_ids.map((fid, i) => <Link key={fid} href={`/findings/${fid}`} className="text-violet-soft hover:text-ink">{i ? ", " : ""}#{i + 1}</Link>)}</p>
      )}
      <p className="text-[11.5px] text-subtle">Generated {timeAgo(analysis.created_at)} from recorded scan evidence. AI can be wrong; verify before acting.</p>
    </div>
  );
}

export function FindingDetailPage({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [fixDialog, setFixDialog] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [paths, setPaths] = useState("");
  const finding = useQuery({ queryKey: ["finding", id], queryFn: () => findingApi.get(id) });
  const ai = useQuery({ queryKey: ["finding-ai", id], queryFn: () => findingApi.ai(id), refetchInterval: (q) => (q.state.data?.active_job ? 2500 : false) });
  const project = useQuery({ queryKey: ["project", finding.data?.project_id], queryFn: () => projectApi.get(finding.data!.project_id), enabled: !!finding.data });
  const fixes = useQuery({ queryKey: ["fixes", "finding", id], queryFn: () => fixApi.list({ finding_id: id }) });
  const fixJobs = useQuery({
    queryKey: ["jobs", id],
    queryFn: () => jobApi.forSubject(id),
    refetchInterval: (q) => (q.state.data?.some((j) => j.kind === "generate_fix" && ACTIVE_JOB.has(j.status)) ? 2500 : false),
  });
  const activeFixJob = fixJobs.data?.find((j) => j.kind === "generate_fix" && ACTIVE_JOB.has(j.status));
  const lastFixJob = fixJobs.data?.find((j) => j.kind === "generate_fix");

  const analyze = useMutation({ mutationFn: () => findingApi.analyze(id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["finding-ai", id] }), onError: (e) => toast.error(errorText(e)) });
  const generate = useMutation({
    mutationFn: () => findingApi.generateFix(id, { instructions: instructions || undefined, file_paths: paths.split(/[\n,]/).map((p) => p.trim()).filter(Boolean) }),
    onSuccess: () => { setFixDialog(false); toast.success("Fix generation started."); void queryClient.invalidateQueries({ queryKey: ["jobs", id] }); },
    onError: (e) => toast.error(errorText(e)),
  });

  // When a fix job finishes, refresh the list so the new proposal appears.
  const finishedFix = lastFixJob?.status === "succeeded" ? lastFixJob.result_id : null;
  const missingFix = !!finishedFix && !!fixes.data && !fixes.data.some((f) => f.id === finishedFix);
  useEffect(() => {
    if (missingFix) void queryClient.invalidateQueries({ queryKey: ["fixes", "finding", id] });
  }, [missingFix, id, queryClient]);

  if (finding.isLoading) return <SkeletonRows rows={6} />;
  if (!finding.data) return <Alert tone="error" title="Finding not available">{errorText(finding.error, "Not found.")}</Alert>;
  const f = finding.data;
  const state = ai.data;
  const hasRepo = !!project.data?.github_repo_id;

  return (
    <>
      <PageHeader
        eyebrow={humanize(f.check_type)}
        title={f.title}
        description={<span className="flex flex-wrap items-center gap-2"><SeverityBadge severity={f.severity} /><ConfidenceBadge value={f.confidence} />{f.http_status && <Badge>HTTP {f.http_status}</Badge>}<span>First seen {timeAgo(f.first_detected_at)}</span></span>}
        actions={<ButtonLink href={`/scans/${f.test_run_id}`} variant="secondary">Open scan report</ButtonLink>}
      />
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader title="What the scanner observed" />
            <div className="space-y-4 p-5">
              <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink/90">{f.description}</p>
              <div>
                <p className="mb-2 text-[12px] font-medium text-muted">Technical evidence (sanitized: tokens, cookies and credentials are removed)</p>
                <pre className="code-font max-h-80 overflow-auto rounded-xl border border-line-soft bg-panel p-4 text-[12px] text-ink/85 scrollbar-thin">{JSON.stringify(f.evidence, null, 2)}</pre>
              </div>
              {f.artifact && (
                // Plain <img>: authenticated API image
                <img src={f.artifact.url} alt="Screenshot taken during the scan" className="w-full rounded-xl border border-line" loading="lazy" />
              )}
            </div>
          </Card>

          <Reveal>
            <Card className="overflow-hidden">
              <CardHeader
                title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-violet-soft" /> AI analysis</span>}
                description="Explains the recorded evidence. Website content is treated as untrusted data."
                action={state?.ai.available && !state.active_job && <Button size="sm" variant={state.analysis ? "secondary" : "primary"} onClick={() => analyze.mutate()} loading={analyze.isPending}>{state.analysis ? "Re-analyze" : "Analyze with AI"}</Button>}
              />
              <div className="p-5">
                {!state ? (
                  <SkeletonRows rows={3} />
                ) : !state.ai.available ? (
                  <Alert tone="info" title="AI is not configured on this server">Set AI_PROVIDER and ANTHROPIC_API_KEY to enable explanations. Fixify never shows simulated AI results.</Alert>
                ) : state.active_job ? (
                  <JobProgress job={state.active_job} label="Analyzing this finding" />
                ) : state.analysis ? (
                  <AnalysisView analysis={state.analysis} />
                ) : (
                  <>
                    {state.last_job?.status === "failed" && <Alert tone="error" title="The last analysis failed" className="mb-4">{state.last_job.error}</Alert>}
                    <p className="text-[13px] text-muted">No analysis yet. Fixify sends the sanitized evidence (never cookies or secrets) to the configured model.</p>
                  </>
                )}
              </div>
            </Card>
          </Reveal>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title={<span className="flex items-center gap-2"><Wrench className="h-4 w-4" /> Proposed fixes</span>} />
            <div className="space-y-3 p-5">
              {activeFixJob && <JobProgress job={activeFixJob} label="Generating a fix from your repository" />}
              {!activeFixJob && lastFixJob?.status === "failed" && <Alert tone="error" title="Fix generation failed">{lastFixJob.error}</Alert>}
              {fixes.data?.map((fix) => (
                <Link key={fix.id} href={`/fixes/${fix.id}`} className="block rounded-xl border border-line-soft bg-panel/60 p-3 transition-colors hover:border-violet/40">
                  <div className="flex items-center justify-between gap-2"><span className="truncate text-[13px] font-medium">{fix.title}</span><span className="text-[11px] text-subtle">v{fix.version}</span></div>
                  <div className="mt-2 flex flex-wrap gap-1.5"><FixStatusBadge status={fix.status} /><ValidationBadge value={fix.validation_status} /></div>
                </Link>
              ))}
              {!hasRepo ? (
                <Alert tone="info" title="Connect a repository">Fixes are generated from your real source code. <Link className="underline" href={`/projects/${f.project_id}`}>Open project settings</Link>.</Alert>
              ) : !state?.ai.available ? null : (
                <Button className="w-full" onClick={() => setFixDialog(true)} disabled={!!activeFixJob}><Sparkles className="h-4 w-4" /> Generate AI fix</Button>
              )}
              <p className="text-[11.5px] text-subtle">Nothing is committed until you approve a fix and request a pull request.</p>
            </div>
          </Card>
          <Card>
            <CardHeader title="Details" />
            <div className="px-5 py-2">
              <KeyValue items={[
                { label: "Project", value: project.data ? <Link className="hover:text-violet-soft" href={`/projects/${project.data.id}`}>{project.data.name}</Link> : "—" },
                { label: "Type", value: humanize(f.finding_type) },
                { label: "Affected URL", value: f.affected_url ? <span className="break-all">{f.affected_url}</span> : "—" },
                { label: "Browser", value: "Headless Chromium" },
                { label: "Recorded", value: formatDateTime(f.created_at) },
                { label: "Repository", value: project.data?.repo_full_name ? <span className="inline-flex items-center gap-1"><FolderGit2 className="h-3.5 w-3.5" />{project.data.repo_full_name}</span> : "—" },
              ]} />
            </div>
          </Card>
        </div>
      </div>

      <Dialog
        open={fixDialog}
        onOpenChange={setFixDialog}
        title="Generate an AI fix"
        description="Fixify reads up to 5 relevant files through the GitHub API (never secrets or build output) and asks the model for the smallest safe change."
        wide
        footer={<><Button variant="ghost" onClick={() => setFixDialog(false)}>Cancel</Button><Button onClick={() => generate.mutate()} loading={generate.isPending}><Sparkles className="h-4 w-4" /> Generate</Button></>}
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="paths" hint="Optional · one per line">Files to change</Label>
            <Textarea id="paths" rows={3} placeholder={"src/app/layout.tsx\npublic/index.html"} value={paths} onChange={(e) => setPaths(e.target.value)} className="font-mono text-[12.5px]" />
            <p className="mt-1 text-[11.5px] text-subtle">Leave empty to let Fixify choose files from the analysis and finding evidence.</p>
          </div>
          <div>
            <Label htmlFor="instructions" hint="Optional">Instructions</Label>
            <Input id="instructions" placeholder="e.g. Keep the existing component structure" value={instructions} onChange={(e) => setInstructions(e.target.value)} maxLength={2000} />
          </div>
        </div>
      </Dialog>
      {finishedFix && !activeFixJob && fixes.data?.[0] && fixes.data[0].status === "pending_review" && fixes.data[0].id === lastFixJob?.result_id && (
        <div className="fixed bottom-5 left-1/2 z-40 -translate-x-1/2">
          <Button onClick={() => router.push(`/fixes/${lastFixJob.result_id}`)} size="lg" className="shadow-[var(--shadow-glow)]"><Sparkles className="h-4 w-4" /> Review the new fix</Button>
        </div>
      )}
    </>
  );
}

export function EmptyFixesHint() {
  return <EmptyState icon={<Sparkles className="h-5 w-5" />} title="No fix proposals yet" description="Open a finding and choose Generate AI fix." />;
}
