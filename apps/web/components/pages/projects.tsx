"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, CalendarClock, Copy, ExternalLink, FolderKanban, FolderPlus, GitBranch, Globe, Play, Radar, Search, Settings2, Trash2, Unlink } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { githubApi, projectApi, scanApi, TERMINAL_STATUSES, type Project, type RunSummary, type Schedule, type ScheduleInput, type Verification } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { projectSchema, type ProjectFormValues } from "@/lib/schemas";
import { formatDateTime, formatDuration, hostname, timeAgo } from "@/lib/utils";
import { RunStatusBadge, SeverityBar, SeverityCounts } from "@/components/status";
import { Button, ButtonLink } from "@/components/ui/button";
import { Dialog, Switch } from "@/components/ui/overlays";
import { Alert, Badge, Card, CardHeader, EmptyState, FieldError, Input, KeyValue, Label, PageHeader, Reveal, Segmented, Select, Skeleton, SkeletonRows, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

// --- List -----------------------------------------------------------------------------------

export function ProjectsPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);
  const projects = useQuery({ queryKey: ["projects", query], queryFn: () => projectApi.list(query || undefined) });

  return (
    <>
      <PageHeader eyebrow="Workspace" title="Projects" description="Websites you test with Fixify. Every project belongs to your account only." actions={<ButtonLink href="/projects/new"><FolderPlus className="h-4 w-4" /> New project</ButtonLink>} />
      <div className="relative mb-5 max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
        <Input aria-label="Search projects" placeholder="Search by name or URL" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {projects.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-44 rounded-[14px]" />)}</div>
      ) : projects.error ? (
        <Alert tone="error" title="Projects could not be loaded">{errorText(projects.error)}</Alert>
      ) : !projects.data?.length ? (
        <Card>
          <EmptyState icon={<FolderKanban className="h-5 w-5" />} title={query ? "No matching projects" : "No projects yet"} description={query ? "Try another search." : "Add the website you want to test. You can connect a GitHub repository later."} action={!query && <ButtonLink href="/projects/new">Create project</ButtonLink>} />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.data.map((project, index) => (
            <Reveal key={project.id} delay={Math.min(index * 0.04, 0.3)}>
              <Link href={`/projects/${project.id}`} className="block h-full">
                <Card hover className="flex h-full flex-col p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-[15px] font-semibold">{project.name}</h3>
                      <p className="mt-0.5 flex items-center gap-1.5 truncate text-[12.5px] text-muted"><Globe className="h-3.5 w-3.5 shrink-0" />{hostname(project.website_url)}</p>
                    </div>
                    {project.latest_scan ? <RunStatusBadge status={project.latest_scan.status} /> : <Badge>Not scanned</Badge>}
                  </div>
                  {project.description && <p className="mt-3 line-clamp-2 text-[12.5px] text-muted">{project.description}</p>}
                  <div className="mt-auto pt-5">
                    <div className="flex items-center justify-between text-[12px] text-muted">
                      <span className="flex items-center gap-1.5">
                        <GitBranch className="h-3.5 w-3.5" />
                        {project.repo_full_name ?? "No repository"}
                      </span>
                      <span>{project.latest_scan ? `${project.latest_scan.findings_count} findings · ${timeAgo(project.latest_scan.created_at)}` : "—"}</span>
                    </div>
                  </div>
                </Card>
              </Link>
            </Reveal>
          ))}
        </div>
      )}
    </>
  );
}

// --- Create / edit form -------------------------------------------------------------------------

function ProjectForm({ initial, submitLabel, onSubmit }: { initial?: Project; submitLabel: string; onSubmit: (values: ProjectFormValues) => Promise<void> }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      name: initial?.name ?? "",
      website_url: initial?.website_url ?? "",
      description: initial?.description ?? "",
      repo_full_name: initial?.repo_full_name ?? "",
      scan_max_links: initial?.scan_max_links?.toString() ?? "",
    },
  });
  const errors = form.formState.errors;
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await onSubmit(values);
    } catch (reason) {
      setError(errorText(reason, "Could not save the project."));
    }
  });
  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      {error && <Alert tone="error">{error}</Alert>}
      <div>
        <Label htmlFor="name">Project name</Label>
        <Input id="name" placeholder="Marketing website" aria-invalid={!!errors.name} {...form.register("name")} />
        <FieldError message={errors.name?.message} />
      </div>
      <div>
        <Label htmlFor="website_url" hint="Must be publicly reachable">Website URL</Label>
        <Input id="website_url" placeholder="https://example.com" inputMode="url" aria-invalid={!!errors.website_url} {...form.register("website_url")} />
        <FieldError message={errors.website_url?.message} />
      </div>
      <div>
        <Label htmlFor="description" hint="Optional">Description</Label>
        <Textarea id="description" rows={2} {...form.register("description")} />
        <FieldError message={errors.description?.message} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <Label htmlFor="repo_full_name" hint="Optional · verified when you connect GitHub">Repository</Label>
          <Input id="repo_full_name" placeholder="owner/repository" aria-invalid={!!errors.repo_full_name} {...form.register("repo_full_name")} disabled={!!initial?.github_repo_id} />
          <FieldError message={errors.repo_full_name?.message} />
        </div>
        <div>
          <Label htmlFor="scan_max_links" hint="0–200, empty = server default">Links checked per scan</Label>
          <Input id="scan_max_links" inputMode="numeric" aria-invalid={!!errors.scan_max_links} {...form.register("scan_max_links")} />
          <FieldError message={errors.scan_max_links?.message} />
        </div>
      </div>
      <Alert tone="info">Only scan websites you own or are authorized to test. Private and internal addresses are blocked by the scanner.</Alert>
      <div className="flex justify-end">
        <Button type="submit" loading={form.formState.isSubmitting}>{submitLabel}</Button>
      </div>
    </form>
  );
}

function toInput(values: ProjectFormValues, keepRepository: boolean) {
  return {
    name: values.name,
    website_url: values.website_url,
    description: values.description || null,
    scan_max_links: values.scan_max_links ? Number(values.scan_max_links) : null,
    ...(keepRepository ? {} : { repo_full_name: values.repo_full_name || null }),
  };
}

export function NewProjectPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return (
    <>
      <PageHeader eyebrow="Projects" title="New project" description="Add a website to scan for real browser errors, broken links, and content issues." />
      <Card className="max-w-2xl p-6">
        <ProjectForm
          submitLabel="Create project"
          onSubmit={async (values) => {
            const project = await projectApi.create(toInput(values, false));
            await queryClient.invalidateQueries({ queryKey: ["projects"] });
            router.push(`/projects/${project.id}`);
          }}
        />
      </Card>
    </>
  );
}

// --- Detail -----------------------------------------------------------------------------------

const isActive = (scan?: RunSummary | null) => !!scan && !TERMINAL_STATUSES.has(scan.status);

function ScanProgress({ scan }: { scan: RunSummary }) {
  return (
    <div className="rounded-xl border border-cyan/25 bg-cyan/[0.05] p-4" role="status" aria-live="polite">
      <div className="flex items-center justify-between text-[13px]">
        <span className="font-medium text-cyan">{scan.status === "queued" ? "Waiting for a scanner…" : "Scanning in a real browser…"}</span>
        <RunStatusBadge status={scan.status} />
      </div>
      <div className="relative mt-3 h-1.5 overflow-hidden rounded-full bg-elevated">
        <div className="absolute inset-y-0 w-1/3 animate-scan rounded-full bg-gradient-to-r from-transparent via-cyan to-transparent" />
      </div>
      <p className="mt-2 text-[12px] text-muted">Usually 5–30 seconds. Results appear here automatically.</p>
    </div>
  );
}

export function ProjectDetailPage({ id }: { id: string }) {
  const [tab, setTab] = useState<"overview" | "repository" | "schedule" | "settings">("overview");
  const queryClient = useQueryClient();
  const toast = useToast();
  const project = useQuery({ queryKey: ["project", id], queryFn: () => projectApi.get(id) });
  const scans = useQuery({
    queryKey: ["project-scans", id],
    queryFn: () => scanApi.forProject(id, 20),
    refetchInterval: (q) => (isActive(q.state.data?.[0]) ? 3000 : false),
  });
  const latest = scans.data?.[0];
  const wasActive = useRef(false);
  useEffect(() => {
    if (isActive(latest)) wasActive.current = true;
    else if (wasActive.current && latest) {
      wasActive.current = false;
      void queryClient.invalidateQueries({ queryKey: ["project", id] });
      toast.success(latest.status === "failed" ? "The scan failed. See the report for details." : `Scan finished with ${latest.findings_count} finding(s).`);
    }
  }, [latest, id, queryClient, toast]);

  const run = useMutation({
    mutationFn: () => scanApi.start(id),
    onSuccess: () => {
      toast.success("Scan queued.");
      void queryClient.invalidateQueries({ queryKey: ["project-scans", id] });
    },
    onError: (error) => toast.error(errorText(error)),
  });

  if (project.isLoading) return <SkeletonRows rows={6} />;
  if (project.error || !project.data) return <Alert tone="error" title="Project not available">{errorText(project.error, "Not found.")}</Alert>;
  const p = project.data;

  return (
    <>
      <PageHeader
        eyebrow="Project"
        title={p.name}
        description={
          <a href={p.website_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 hover:text-ink">
            {p.website_url} <ExternalLink className="h-3.5 w-3.5" />
          </a>
        }
        actions={
          <Button onClick={() => run.mutate()} loading={run.isPending} disabled={isActive(latest)}>
            <Play className="h-4 w-4" /> {isActive(latest) ? "Scan in progress" : "Run scan"}
          </Button>
        }
      />
      <div className="mb-5">
        <Segmented
          label="project-tabs"
          value={tab}
          onChange={setTab}
          options={[
            { value: "overview", label: "Overview" },
            { value: "repository", label: "Repository" },
            { value: "schedule", label: "Schedule" },
            { value: "settings", label: "Settings" },
          ]}
        />
      </div>
      {tab === "overview" && <ProjectOverview project={p} scans={scans.data} loading={scans.isLoading} />}
      {tab === "repository" && <RepositoryPanel project={p} />}
      {tab === "schedule" && <SchedulePanel projectId={p.id} />}
      {tab === "settings" && <SettingsPanel project={p} />}
    </>
  );
}

function ProjectOverview({ project, scans, loading }: { project: Project; scans?: RunSummary[]; loading: boolean }) {
  const latest = scans?.[0];
  const lastFinished = scans?.find((scan) => scan.status === "completed" || scan.status === "completed_with_errors");
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        {latest && isActive(latest) && <ScanProgress scan={latest} />}
        <VerificationNotice project={project} />
        <Card>
          <CardHeader title="Latest findings" description={lastFinished ? `From the scan ${timeAgo(lastFinished.created_at)}` : "Run a scan to see results"} action={lastFinished && <ButtonLink href={`/scans/${lastFinished.id}`} size="sm" variant="secondary">Open report</ButtonLink>} />
          <div className="p-5">
            {lastFinished ? (
              <>
                <div className="mb-4 flex items-baseline gap-2">
                  <span className="text-[30px] font-semibold tabular-nums">{lastFinished.findings_count}</span>
                  <span className="text-[13px] text-muted">findings · {lastFinished.checks_passed}/{lastFinished.checks_total} checks passed · {formatDuration(lastFinished.duration_ms)}</span>
                </div>
                <SeverityCounts counts={lastFinished.severity_counts} />
              </>
            ) : (
              <p className="text-[13px] text-muted">No completed scan yet.</p>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="Scan history" />
          {loading ? (
            <SkeletonRows />
          ) : !scans?.length ? (
            <EmptyState icon={<Radar className="h-5 w-5" />} title="No scans yet" description="Press Run scan to open the website in headless Chromium." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-[13px]">
                <thead className="text-[11px] uppercase tracking-wider text-subtle">
                  <tr><th className="px-5 py-2.5 font-medium">Started</th><th className="font-medium">Status</th><th className="font-medium">Findings</th><th className="font-medium">Duration</th><th className="px-5 font-medium">Trigger</th></tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {scans.map((scan) => (
                    <tr key={scan.id} className="transition-colors hover:bg-elevated/40">
                      <td className="px-5 py-3"><Link className="hover:text-violet-soft" href={`/scans/${scan.id}`}>{formatDateTime(scan.created_at)}</Link></td>
                      <td><RunStatusBadge status={scan.status} /></td>
                      <td><div className="flex items-center gap-2"><span className="w-6 tabular-nums">{scan.findings_count}</span><SeverityBar counts={scan.severity_counts} className="w-24" /></div></td>
                      <td className="tabular-nums text-muted">{formatDuration(scan.duration_ms)}</td>
                      <td className="px-5 capitalize text-muted">{scan.trigger}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      <Card className="h-fit">
        <CardHeader title="Details" />
        <div className="px-5 py-2">
          <KeyValue
            items={[
              { label: "Website", value: hostname(project.website_url) },
              { label: "Repository", value: project.repo_full_name ? <span className="inline-flex items-center gap-1.5"><GitBranch className="h-3.5 w-3.5" />{project.repo_full_name}</span> : "Not connected" },
              { label: "Branch", value: project.default_branch ?? "—" },
              { label: "Links per scan", value: project.scan_max_links ?? "Server default" },
              { label: "Created", value: formatDateTime(project.created_at) },
              { label: "Last scan", value: latest ? timeAgo(latest.created_at) : "Never" },
            ]}
          />
          {project.description && <p className="border-t border-line-soft py-3 text-[13px] text-muted">{project.description}</p>}
        </div>
      </Card>
    </div>
  );
}

function RepositoryPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const status = useQuery({ queryKey: ["github-status"], queryFn: githubApi.status });
  const connected = status.data?.connected;
  const repos = useQuery({ queryKey: ["github-repos"], queryFn: githubApi.repositories, enabled: !!connected });
  const [repo, setRepo] = useState(project.repo_full_name ?? "");
  const branches = useQuery({ queryKey: ["github-branches", repo], queryFn: () => githubApi.branches(repo), enabled: !!connected && /^[^/]+\/[^/]+$/.test(repo) });
  const [branch, setBranch] = useState(project.default_branch ?? "");
  const refresh = (updated: Project) => {
    queryClient.setQueryData(["project", project.id], updated);
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
  };
  const link = useMutation({
    mutationFn: () => projectApi.connectRepository(project.id, repo, branch || undefined),
    onSuccess: (updated) => {
      refresh(updated);
      toast.success(`Connected ${updated.repo_full_name}.`);
    },
    onError: (error) => toast.error(errorText(error)),
  });
  const unlink = useMutation({ mutationFn: () => projectApi.disconnectRepository(project.id), onSuccess: (updated) => { refresh(updated); setRepo(""); setBranch(""); toast.success("Repository disconnected."); } });

  if (status.isLoading) return <SkeletonRows />;
  if (!status.data?.configured) return <Alert tone="info" title="GitHub integration is not configured">The server needs GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, and TOKEN_ENCRYPTION_KEY. Scans keep working without it.</Alert>;
  if (!connected) {
    return (
      <Card>
        <EmptyState icon={<GitBranch className="h-5 w-5" />} title="Connect GitHub first" description="Fixify reads source files through the GitHub API to propose fixes. It never clones or runs your code." action={<ButtonLink href="/github">Connect GitHub</ButtonLink>} />
      </Card>
    );
  }
  return (
    <Card className="max-w-2xl">
      <CardHeader title="Repository" description="Fixes are proposed against this branch and opened as pull requests on new branches." />
      <div className="space-y-5 p-5">
        {project.github_repo_id && (
          <Alert tone="success" title={`Connected to ${project.repo_full_name}`} action={<Button size="sm" variant="ghost" onClick={() => unlink.mutate()} loading={unlink.isPending}><Unlink className="h-4 w-4" /> Disconnect</Button>}>
            Branch <span className="font-mono">{project.default_branch}</span>
          </Alert>
        )}
        <div>
          <Label htmlFor="repo">Repository</Label>
          {repos.isLoading ? <Skeleton className="h-10" /> : (
            <Select id="repo" value={repo} onChange={(e) => { setRepo(e.target.value); setBranch(""); }}>
              <option value="">Select a repository…</option>
              {repos.data?.map((r) => <option key={r.id} value={r.full_name}>{r.full_name}{r.private ? " (private)" : ""}{r.can_push ? "" : " — read only"}</option>)}
            </Select>
          )}
          {repos.error && <FieldError message={errorText(repos.error)} />}
        </div>
        <div>
          <Label htmlFor="branch" hint="Default branch if empty">Branch</Label>
          <Select id="branch" value={branch} onChange={(e) => setBranch(e.target.value)} disabled={!repo}>
            <option value="">Default branch</option>
            {branches.data?.map((name) => <option key={name} value={name}>{name}</option>)}
          </Select>
        </div>
        <div className="flex justify-end">
          <Button onClick={() => link.mutate()} loading={link.isPending} disabled={!repo}>Save repository</Button>
        </div>
      </div>
    </Card>
  );
}

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function SchedulePanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const schedule = useQuery({ queryKey: ["schedule", projectId], queryFn: () => projectApi.schedule(projectId) });
  const [draft, setDraft] = useState<ScheduleInput>({ enabled: true, frequency: "daily", hour_utc: 3, weekday: 0, interval_hours: 24 });
  useEffect(() => {
    if (schedule.data) setDraft({ enabled: schedule.data.enabled, frequency: schedule.data.frequency, hour_utc: schedule.data.hour_utc, weekday: schedule.data.weekday ?? 0, interval_hours: schedule.data.interval_hours ?? 24 });
  }, [schedule.data]);
  const save = useMutation({
    mutationFn: () => projectApi.saveSchedule(projectId, { ...draft, weekday: draft.frequency === "weekly" ? draft.weekday : null, interval_hours: draft.frequency === "custom" ? draft.interval_hours : null }),
    onSuccess: (data: Schedule) => { queryClient.setQueryData(["schedule", projectId], data); toast.success(data.enabled ? `Next scan ${timeAgo(data.next_run_at)}.` : "Scheduled scans paused."); },
    onError: (error) => toast.error(errorText(error)),
  });
  const remove = useMutation({ mutationFn: () => projectApi.deleteSchedule(projectId), onSuccess: () => { queryClient.setQueryData(["schedule", projectId], null); toast.success("Schedule removed."); } });
  if (schedule.isLoading) return <SkeletonRows />;
  const s = schedule.data;
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader title="Scheduled scans" description="Fixify's worker starts these scans for you; times are in UTC." action={<Switch label="Enable scheduled scans" checked={draft.enabled} onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} />} />
        <div className="grid gap-5 p-5 sm:grid-cols-3">
          <div>
            <Label htmlFor="frequency">Frequency</Label>
            <Select id="frequency" value={draft.frequency} onChange={(e) => setDraft({ ...draft, frequency: e.target.value as ScheduleInput["frequency"] })}>
              <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="custom">Every N hours</option>
            </Select>
          </div>
          {draft.frequency === "weekly" && (
            <div>
              <Label htmlFor="weekday">Day</Label>
              <Select id="weekday" value={draft.weekday ?? 0} onChange={(e) => setDraft({ ...draft, weekday: Number(e.target.value) })}>
                {WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
              </Select>
            </div>
          )}
          {draft.frequency === "custom" ? (
            <div>
              <Label htmlFor="interval" hint="minimum 6">Every (hours)</Label>
              <Input id="interval" type="number" min={6} max={720} value={draft.interval_hours ?? 24} onChange={(e) => setDraft({ ...draft, interval_hours: Number(e.target.value) })} />
            </div>
          ) : (
            <div>
              <Label htmlFor="hour">Time (UTC)</Label>
              <Select id="hour" value={draft.hour_utc} onChange={(e) => setDraft({ ...draft, hour_utc: Number(e.target.value) })}>
                {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
              </Select>
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-line-soft px-5 py-4">
          {s && <Button variant="ghost" onClick={() => remove.mutate()} loading={remove.isPending}>Remove schedule</Button>}
          <Button onClick={() => save.mutate()} loading={save.isPending}><CalendarClock className="h-4 w-4" /> Save schedule</Button>
        </div>
      </Card>
      <Card className="h-fit">
        <CardHeader title="Status" />
        <div className="px-5 py-2">
          <KeyValue items={[
            { label: "State", value: s ? (s.enabled ? <Badge tone="success" dot>Active</Badge> : <Badge>Paused</Badge>) : "Not scheduled" },
            { label: "Next scan", value: s?.next_run_at ? `${formatDateTime(s.next_run_at)} (${timeAgo(s.next_run_at)})` : "—" },
            { label: "Last scheduled run", value: s?.last_run_at ? formatDateTime(s.last_run_at) : "—" },
            { label: "Last outcome", value: s?.last_outcome ?? "—" },
          ]} />
          {s?.last_run_id && <Link href={`/scans/${s.last_run_id}`} className="mb-2 block text-[12.5px] text-violet-soft hover:text-ink">Open last scheduled scan →</Link>}
        </div>
      </Card>
    </div>
  );
}

function SettingsPanel({ project }: { project: Project }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [typed, setTyped] = useState("");
  const remove = useMutation({
    mutationFn: () => projectApi.remove(project.id),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["projects"] }); toast.success("Project deleted."); router.push("/projects"); },
    onError: (error) => toast.error(errorText(error)),
  });
  return (
    <div className="grid max-w-3xl gap-5">
      <VerificationPanel project={project} />
      <Card>
        <CardHeader title={<span className="flex items-center gap-2"><Settings2 className="h-4 w-4" /> Project settings</span>} />
        <div className="p-5">
          <ProjectForm
            initial={project}
            submitLabel="Save changes"
            onSubmit={async (values) => {
              const updated = await projectApi.update(project.id, toInput(values, !!project.github_repo_id));
              queryClient.setQueryData(["project", project.id], { ...project, ...updated });
              await queryClient.invalidateQueries({ queryKey: ["projects"] });
              toast.success("Project saved.");
            }}
          />
        </div>
      </Card>
      <Card className="border-critical/30">
        <CardHeader title="Delete project" description="Removes the project with all scans, findings, screenshots, AI analyses, and fix proposals. Pull requests on GitHub are not touched." action={<Button variant="danger" onClick={() => setConfirm(true)}><Trash2 className="h-4 w-4" /> Delete</Button>} />
      </Card>
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Delete this project?"
        description="This cannot be undone."
        footer={<><Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="danger" disabled={typed !== project.name} loading={remove.isPending} onClick={() => remove.mutate()}>Delete permanently</Button></>}
      >
        <Label htmlFor="confirm-name">Type <span className="font-mono text-ink">{project.name}</span> to confirm</Label>
        <Input id="confirm-name" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
      </Dialog>
    </div>
  );
}

// --- Ownership verification ---------------------------------------------------------------------

function VerificationNotice({ project }: { project: Project }) {
  const state = useQuery({ queryKey: ["verification", project.id], queryFn: () => projectApi.verification(project.id) });
  if (!state.data?.required || state.data.verified) return null;
  return (
    <Alert tone="warning" title="Verify that you control this website">
      Scans are blocked until {state.data.host} is verified. Open the <strong>Settings</strong> tab and follow the ownership verification steps.
    </Alert>
  );
}

function CopyField({ label, value }: { label: string; value: string }) {
  const toast = useToast();
  return (
    <div>
      <Label>{label}</Label>
      <div className="flex gap-2">
        <code className="code-font min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg border border-line bg-panel px-3 py-2.5 text-ink/90 scrollbar-thin">{value}</code>
        <Button
          variant="secondary"
          size="icon"
          aria-label={`Copy ${label}`}
          onClick={() => navigator.clipboard.writeText(value).then(() => toast.success("Copied."), () => toast.error("Copy failed."))}
        >
          <Copy className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function VerificationPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const state = useQuery({ queryKey: ["verification", project.id], queryFn: () => projectApi.verification(project.id) });
  const check = useMutation({
    mutationFn: () => projectApi.checkVerification(project.id),
    onSuccess: (data: Verification) => {
      queryClient.setQueryData(["verification", project.id], data);
      void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
      toast.success(`${data.host} is verified.`);
    },
    onError: (error) => toast.error(errorText(error)),
  });
  const v = state.data;
  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><BadgeCheck className="h-4 w-4" /> Ownership verification</span>}
        description={v?.required ? "Required on this server before a website can be scanned." : "Optional on this server. Proves you control the website."}
        action={v?.verified ? <Badge tone="success" dot>Verified</Badge> : v ? <Badge tone={v.required ? "warning" : "neutral"}>Not verified</Badge> : null}
      />
      <div className="space-y-4 p-5">
        {!v ? (
          <SkeletonRows rows={2} />
        ) : v.verified ? (
          <p className="text-[13px] text-muted">
            {v.host} was verified {timeAgo(v.verified_at)} using the {v.method === "file" ? "verification file" : "meta tag"}. Changing the website to another host requires verifying again.
          </p>
        ) : (
          <>
            <p className="text-[13px] text-muted">Publish the token on <span className="font-mono text-ink/90">{v.host}</span> with either method, then press Check. Fixify fetches it through the same protected proxy as scans.</p>
            <CopyField label="Option 1 · add to the <head> of your home page" value={v.meta_tag} />
            <CopyField label={`Option 2 · serve this text at ${v.file_url}`} value={v.token} />
          </>
        )}
      </div>
      {v && !v.verified && (
        <div className="flex justify-end border-t border-line-soft px-5 py-3">
          <Button onClick={() => check.mutate()} loading={check.isPending}><BadgeCheck className="h-4 w-4" /> Check verification</Button>
        </div>
      )}
    </Card>
  );
}
