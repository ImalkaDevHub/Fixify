"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, GitPullRequest, Loader2, MessageSquare, RefreshCw, RotateCcw, ShieldCheck, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ACTIVE_JOB, fixApi, jobApi, projectApi, type FixDetail, type FixStatus, type Review } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { cn, formatDateTime, timeAgo } from "@/lib/utils";
import { DiffViewer } from "@/components/diff-viewer";
import { EmptyFixesHint } from "@/components/pages/findings";
import { ConfidenceBadge, FixStatusBadge, SeverityBadge, ValidationBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/overlays";
import { Alert, Badge, Card, CardHeader, KeyValue, PageHeader, Reveal, Segmented, SkeletonRows, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

export function FixesPage() {
  const [status, setStatus] = useState<FixStatus | "all">("pending_review");
  const fixes = useQuery({ queryKey: ["fixes", status], queryFn: () => fixApi.list(status === "all" ? {} : { status }) });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => projectApi.list() });
  const names = new Map(projects.data?.map((p) => [p.id, p.name]));
  return (
    <>
      <PageHeader eyebrow="Human review" title="AI Fixes" description="Proposed code changes waiting for your decision. Approved fixes become pull requests; nothing is merged automatically." />
      <div className="mb-5">
        <Segmented
          label="fix-status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "pending_review", label: "Pending review" },
            { value: "approved", label: "Approved" },
            { value: "applied", label: "Applied" },
            { value: "failed_validation", label: "Failed validation" },
            { value: "rejected", label: "Rejected" },
            { value: "all", label: "All" },
          ]}
        />
      </div>
      <Card>
        {fixes.isLoading ? (
          <SkeletonRows rows={5} />
        ) : !fixes.data?.length ? (
          <EmptyFixesHint />
        ) : (
          <ul className="divide-y divide-line-soft">
            {fixes.data.map((fix) => (
              <li key={fix.id}>
                <Link href={`/fixes/${fix.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-elevated/40">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13.5px] font-medium">{fix.title}</p>
                    <p className="truncate text-[12px] text-muted">{names.get(fix.project_id)} · {fix.repo_full_name}@{fix.base_branch} · {fix.files.join(", ")}</p>
                  </div>
                  <ValidationBadge value={fix.validation_status} />
                  <FixStatusBadge status={fix.status} />
                  <span className="w-20 text-right text-[12px] text-subtle">{timeAgo(fix.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

const REVIEW_LABEL: Record<Review["action"], string> = { comment: "commented", approve: "approved", reject: "rejected", reopen: "reopened" };

function Timeline({ fix }: { fix: FixDetail }) {
  const items = [
    { key: "created", icon: Sparkles, text: `AI proposed version ${fix.version}`, at: fix.created_at, detail: null as string | null },
    ...fix.reviews.map((review) => ({ key: review.id, icon: review.action === "approve" ? Check : review.action === "reject" ? X : review.action === "reopen" ? RotateCcw : MessageSquare, text: `You ${REVIEW_LABEL[review.action]}`, at: review.created_at, detail: review.comment })),
    ...(fix.pull_request?.number ? [{ key: "pr", icon: GitPullRequest, text: `Pull request #${fix.pull_request.number} opened`, at: fix.pull_request.created_at, detail: null }] : []),
  ];
  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {items.map(({ key, icon: Icon, text, at, detail }) => (
        <li key={key} className="relative">
          <span className="absolute -left-[27px] flex h-[22px] w-[22px] items-center justify-center rounded-full border border-line bg-card text-violet-soft"><Icon className="h-3 w-3" /></span>
          <p className="text-[13px]">{text} <span className="text-subtle">· {timeAgo(at)}</span></p>
          {detail && <p className="mt-1 whitespace-pre-wrap rounded-lg border border-line-soft bg-panel/60 px-3 py-2 text-[12.5px] text-ink/85">{detail}</p>}
        </li>
      ))}
    </ol>
  );
}

export function FixDetailPage({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [regenOpen, setRegenOpen] = useState(false);
  const [regenText, setRegenText] = useState("");
  const [prJobId, setPrJobId] = useState<string | null>(null);
  const fix = useQuery({ queryKey: ["fix", id], queryFn: () => fixApi.get(id), refetchInterval: (q) => (q.state.data?.pull_request?.status === "creating" ? 2500 : false) });
  const prJob = useQuery({ queryKey: ["job", prJobId], queryFn: () => jobApi.get(prJobId!), enabled: !!prJobId, refetchInterval: (q) => (q.state.data && ACTIVE_JOB.has(q.state.data.status) ? 2000 : false) });
  const [regenJobId, setRegenJobId] = useState<string | null>(null);
  const regenJob = useQuery({ queryKey: ["job", regenJobId], queryFn: () => jobApi.get(regenJobId!), enabled: !!regenJobId, refetchInterval: (q) => (q.state.data && ACTIVE_JOB.has(q.state.data.status) ? 2000 : false) });

  useEffect(() => {
    if (prJob.data && !ACTIVE_JOB.has(prJob.data.status)) {
      void queryClient.invalidateQueries({ queryKey: ["fix", id] });
      if (prJob.data.status === "succeeded") toast.success("Pull request created.");
      else toast.error(prJob.data.error ?? "The pull request could not be created.");
      setPrJobId(null);
    }
  }, [prJob.data, id, queryClient, toast]);
  useEffect(() => {
    if (regenJob.data && !ACTIVE_JOB.has(regenJob.data.status)) {
      setRegenJobId(null);
      if (regenJob.data.status === "succeeded" && regenJob.data.result_id) router.push(`/fixes/${regenJob.data.result_id}`);
      else toast.error(regenJob.data.error ?? "Regeneration failed.");
    }
  }, [regenJob.data, router, toast]);

  const review = useMutation({
    mutationFn: ({ action, text }: { action: Review["action"]; text?: string }) => fixApi.review(id, action, text),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["fix", id], data);
      void queryClient.invalidateQueries({ queryKey: ["fixes"] });
      if (variables.action === "comment") setComment("");
      toast.success(variables.action === "comment" ? "Comment added." : `Fix ${REVIEW_LABEL[variables.action]}.`);
    },
    onError: (error) => toast.error(errorText(error)),
  });
  const createPr = useMutation({ mutationFn: () => fixApi.createPullRequest(id), onSuccess: (job) => { setPrJobId(job.id); void queryClient.invalidateQueries({ queryKey: ["fix", id] }); }, onError: (e) => toast.error(errorText(e)) });
  const refreshPr = useMutation({ mutationFn: () => fixApi.refreshPullRequest(id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["fix", id] }), onError: (e) => toast.error(errorText(e)) });
  const regenerate = useMutation({ mutationFn: () => fixApi.regenerate(id, regenText), onSuccess: (job) => { setRegenOpen(false); setRegenJobId(job.id); toast.success("Regenerating with your feedback…"); }, onError: (e) => toast.error(errorText(e)) });

  if (fix.isLoading) return <SkeletonRows rows={8} />;
  if (!fix.data) return <Alert tone="error" title="Fix not available">{errorText(fix.error, "Not found.")}</Alert>;
  const f = fix.data;
  const pr = f.pull_request;
  const creating = !!prJobId || pr?.status === "creating";

  return (
    <>
      <PageHeader
        eyebrow={`AI fix · version ${f.version}`}
        title={f.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <FixStatusBadge status={f.status} />
            <ValidationBadge value={f.validation_status} />
            <ConfidenceBadge value={f.confidence} />
            {f.finding_severity && <SeverityBadge severity={f.finding_severity} />}
            <span className="font-mono text-[12px]">{f.repo_full_name}@{f.base_branch}</span>
          </span>
        }
        actions={<Link href={`/findings/${f.finding_id}`} className="text-[13px] text-violet-soft hover:text-ink">View finding</Link>}
      />

      {regenJobId && <Alert tone="info" className="mb-5" title="Generating a new version"><span className="inline-flex items-center gap-2"><Loader2 className="h-3.5 w-3.5 animate-spin" /> You will be taken to it when it is ready.</span></Alert>}
      {f.validation_status === "failed" && (
        <Alert tone="error" className="mb-5" title="This proposal failed validation and cannot be approved">
          <ul className="list-disc pl-4">{f.validation_messages.map((m) => <li key={m}>{m}</li>)}</ul>
        </Alert>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-5">
          <Reveal>
            <Card>
              <CardHeader title="What changes and why" />
              <div className="grid gap-4 p-5 md:grid-cols-2">
                <div>
                  <p className="mb-1 text-[12px] font-semibold uppercase tracking-wider text-violet-soft">Explanation</p>
                  <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink/90">{f.explanation}</p>
                </div>
                <div>
                  <p className="mb-1 text-[12px] font-semibold uppercase tracking-wider text-violet-soft">Potential impact</p>
                  <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink/90">{f.impact}</p>
                </div>
              </div>
            </Card>
          </Reveal>
          {f.changes.map((change, index) => (
            <Reveal key={change.path} delay={0.05 * (index + 1)}>
              <DiffViewer change={change} />
              {change.edits.some((e) => e.reason) && (
                <ul className="mt-2 space-y-1 px-1 text-[12.5px] text-muted">
                  {change.edits.map((edit, i) => edit.reason && <li key={i}>• {edit.reason}</li>)}
                </ul>
              )}
            </Reveal>
          ))}
          {f.validation_status !== "failed" && f.validation_messages.length > 0 && (
            <Alert tone="info" title="Validation notes"><ul className="list-disc pl-4">{f.validation_messages.map((m) => <li key={m}>{m}</li>)}</ul></Alert>
          )}
        </div>

        <div className="space-y-5">
          <Card className="xl:sticky xl:top-20">
            <CardHeader title="Your decision" description="Approval only marks the fix as accepted. Creating a pull request is a separate step." />
            <div className="space-y-3 p-5">
              {f.status === "pending_review" && (
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="success" onClick={() => review.mutate({ action: "approve", text: comment || undefined })} loading={review.isPending && review.variables?.action === "approve"}><Check className="h-4 w-4" /> Approve</Button>
                  <Button variant="danger" onClick={() => review.mutate({ action: "reject", text: comment || undefined })} loading={review.isPending && review.variables?.action === "reject"}><X className="h-4 w-4" /> Reject</Button>
                </div>
              )}
              {f.status === "approved" && !pr?.number && (
                <Button className="w-full" onClick={() => createPr.mutate()} loading={createPr.isPending || creating} disabled={creating}>
                  <GitPullRequest className="h-4 w-4" /> {creating ? "Creating pull request…" : "Create pull request"}
                </Button>
              )}
              {f.status === "approved" && <Button variant="ghost" className="w-full" onClick={() => review.mutate({ action: "reject" })}>Withdraw approval</Button>}
              {(f.status === "rejected" || f.status === "superseded") && (
                <Button variant="secondary" className="w-full" onClick={() => review.mutate({ action: "reopen" })}><RotateCcw className="h-4 w-4" /> Reopen proposal</Button>
              )}
              {f.status !== "applied" && (
                <Button variant="outline" className="w-full" onClick={() => setRegenOpen(true)} disabled={!!regenJobId}><RefreshCw className="h-4 w-4" /> Regenerate with feedback</Button>
              )}
              <div>
                <label htmlFor="comment" className="sr-only">Review comment</label>
                <Textarea id="comment" rows={3} placeholder="Leave a review comment…" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={5000} />
                <Button size="sm" variant="secondary" className="mt-2" disabled={!comment.trim()} onClick={() => review.mutate({ action: "comment", text: comment })}><MessageSquare className="h-3.5 w-3.5" /> Comment</Button>
              </div>
            </div>
          </Card>

          {pr && (
            <Card>
              <CardHeader title={<span className="flex items-center gap-2"><GitPullRequest className="h-4 w-4" /> Pull request</span>} action={pr.number ? <Button size="sm" variant="ghost" onClick={() => refreshPr.mutate()} loading={refreshPr.isPending} aria-label="Refresh status"><RefreshCw className="h-3.5 w-3.5" /></Button> : null} />
              <div className="space-y-2 p-5 text-[13px]">
                <div className="flex items-center gap-2">
                  <Badge tone={pr.status === "open" ? "success" : pr.status === "merged" ? "violet" : pr.status === "failed" ? "critical" : pr.status === "creating" ? "cyan" : "neutral"}>{pr.status}</Badge>
                  {pr.number && <span>#{pr.number}</span>}
                </div>
                {pr.error && <Alert tone="error">{pr.error}</Alert>}
                <p className="font-mono text-[12px] text-muted">{pr.branch_name} → {pr.base_branch}</p>
                {pr.url && <a href={pr.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 text-violet-soft hover:text-ink">Open on GitHub <ExternalLink className="h-3.5 w-3.5" /></a>}
                {pr.status === "failed" && f.status === "approved" && <Button size="sm" onClick={() => createPr.mutate()} loading={createPr.isPending}>Try again</Button>}
                <p className="text-[11.5px] text-subtle">Fixify never merges. Review and merge on GitHub.{pr.last_synced_at ? ` Synced ${timeAgo(pr.last_synced_at)}.` : ""}</p>
              </div>
            </Card>
          )}

          <Card>
            <CardHeader title="History" />
            <div className="p-5 pl-8"><Timeline fix={f} /></div>
          </Card>
          <Card>
            <CardHeader title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-success" /> Provenance</span>} />
            <div className="px-5 py-2">
              <KeyValue items={[
                { label: "Model", value: f.model },
                { label: "Base commit", value: <span className="font-mono">{f.base_commit_sha.slice(0, 10)}</span> },
                { label: "Files", value: f.changes.length },
                { label: "Created", value: formatDateTime(f.created_at) },
                { label: "Reviewed", value: formatDateTime(f.reviewed_at) },
              ]} />
            </div>
          </Card>
        </div>
      </div>

      <Dialog
        open={regenOpen}
        onOpenChange={setRegenOpen}
        title="Regenerate this fix"
        description="Your review comments and these instructions are given to the model. A new version is created; this one is kept in the history."
        footer={<><Button variant="ghost" onClick={() => setRegenOpen(false)}>Cancel</Button><Button onClick={() => regenerate.mutate()} loading={regenerate.isPending}><Sparkles className="h-4 w-4" /> Regenerate</Button></>}
      >
        <Textarea rows={4} placeholder="What should be different?" value={regenText} onChange={(e) => setRegenText(e.target.value)} maxLength={2000} aria-label="Regeneration instructions" />
      </Dialog>
      <span className={cn("sr-only")} aria-live="polite">{creating ? "Creating pull request" : ""}</span>
    </>
  );
}
