"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, GitBranch, Lock, ShieldCheck, Unlink } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { githubApi, projectApi } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { formatDate } from "@/lib/utils";
import { Button, ButtonLink } from "@/components/ui/button";
import { Dialog } from "@/components/ui/overlays";
import { Alert, Badge, Card, CardHeader, EmptyState, PageHeader, SkeletonRows } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

export function GitHubPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const status = useQuery({ queryKey: ["github-status"], queryFn: githubApi.status });
  const repos = useQuery({ queryKey: ["github-repos"], queryFn: githubApi.repositories, enabled: !!status.data?.connected });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => projectApi.list() });
  const connect = useMutation({
    mutationFn: githubApi.connect,
    onSuccess: ({ authorize_url }) => {
      // The URL comes from our own API (GitHub or GitHub Enterprise). Only HTTPS targets are
      // followed, plus plain HTTP on loopback for local test setups.
      if (/^https:\/\//.test(authorize_url) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//.test(authorize_url)) {
        window.location.assign(authorize_url);
      } else {
        toast.error("The GitHub authorization address is not allowed.");
      }
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const disconnect = useMutation({
    mutationFn: githubApi.disconnect,
    onSuccess: () => { setConfirm(false); void queryClient.invalidateQueries({ queryKey: ["github-status"] }); toast.success("GitHub disconnected and token deleted."); },
    onError: (e) => toast.error(errorText(e)),
  });
  const linked = projects.data?.filter((p) => p.repo_full_name) ?? [];

  return (
    <>
      <PageHeader eyebrow="Integrations" title="GitHub" description="Connect GitHub so Fixify can read relevant source files and open pull requests for fixes you approve." />
      {status.isLoading ? (
        <SkeletonRows />
      ) : !status.data?.configured ? (
        <Alert tone="info" title="GitHub integration is not configured on this server">An administrator must set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, and TOKEN_ENCRYPTION_KEY. See docs/github-oauth.md.</Alert>
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <Card>
              <CardHeader title="Account" action={status.data.connected ? <Button variant="danger" size="sm" onClick={() => setConfirm(true)}><Unlink className="h-4 w-4" /> Disconnect</Button> : null} />
              <div className="p-5">
                {status.data.connected ? (
                  <div className="flex items-center gap-4">
                    {status.data.avatar_url && /^https:\/\/avatars\.githubusercontent\.com\//.test(status.data.avatar_url) ? (
                      // Plain <img>: GitHub avatar, allowed by CSP
                      <img src={status.data.avatar_url} alt="" className="h-12 w-12 rounded-full border border-line" />
                    ) : (
                      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-elevated"><GitBranch className="h-5 w-5" /></span>
                    )}
                    <div>
                      <p className="flex items-center gap-2 text-[15px] font-semibold">@{status.data.login} <Badge tone="success" dot>Connected</Badge></p>
                      <p className="text-[12.5px] text-muted">Since {formatDate(status.data.connected_at)} · scopes: {status.data.scopes.join(", ") || "none"}</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      {status.data.status === "revoked" && <Alert tone="warning" className="mb-3" title="Access was revoked">GitHub rejected the stored token. Connect again to continue.</Alert>}
                      <p className="text-[13.5px] text-ink/90">Not connected.</p>
                      <p className="text-[12.5px] text-muted">You will be sent to GitHub to authorize Fixify.</p>
                    </div>
                    <Button onClick={() => connect.mutate()} loading={connect.isPending}><GitBranch className="h-4 w-4" /> Connect GitHub</Button>
                  </div>
                )}
              </div>
            </Card>
            {status.data.connected && (
              <Card>
                <CardHeader title="Accessible repositories" description="Link one to a project from the project's Repository tab." />
                {repos.isLoading ? (
                  <SkeletonRows />
                ) : repos.error ? (
                  <div className="p-5"><Alert tone="error">{errorText(repos.error)}</Alert></div>
                ) : !repos.data?.length ? (
                  <EmptyState icon={<GitBranch className="h-5 w-5" />} title="No repositories" description="Your account has no repositories Fixify can access." />
                ) : (
                  <ul className="max-h-[420px] divide-y divide-line-soft overflow-y-auto scrollbar-thin">
                    {repos.data.map((repo) => (
                      <li key={repo.id} className="flex items-center gap-3 px-5 py-3">
                        <div className="min-w-0 flex-1">
                          <p className="flex items-center gap-2 truncate text-[13.5px] font-medium">{repo.private && <Lock className="h-3.5 w-3.5 text-subtle" />}{repo.full_name}</p>
                          {repo.description && <p className="truncate text-[12px] text-muted">{repo.description}</p>}
                        </div>
                        <Badge tone={repo.can_push ? "success" : "neutral"}>{repo.can_push ? "Can open PRs" : "Read only"}</Badge>
                        {repo.html_url && <a href={repo.html_url} target="_blank" rel="noreferrer noopener" aria-label={`Open ${repo.full_name} on GitHub`} className="text-muted hover:text-ink"><ExternalLink className="h-4 w-4" /></a>}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
          </div>
          <div className="space-y-5">
            <Card>
              <CardHeader title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-success" /> How Fixify uses GitHub</span>} />
              <ul className="space-y-2.5 p-5 text-[13px] text-ink/85">
                {[
                  "Your token is encrypted at rest and never sent to the browser.",
                  "Files are read one by one through the API; repositories are never cloned or executed.",
                  "Secrets files, dependencies and build output are never read.",
                  "Changes are pushed only to new fixify/* branches, after you approve them.",
                  "Pull requests are never merged by Fixify.",
                ].map((text) => <li key={text} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />{text}</li>)}
              </ul>
            </Card>
            <Card>
              <CardHeader title="Linked projects" />
              <ul className="divide-y divide-line-soft">
                {linked.length ? linked.map((p) => (
                  <li key={p.id} className="px-5 py-3 text-[13px]"><a href={`/projects/${p.id}`} className="font-medium hover:text-violet-soft">{p.name}</a><p className="font-mono text-[12px] text-muted">{p.repo_full_name}@{p.default_branch ?? "default"}</p></li>
                )) : <li className="px-5 py-4 text-[13px] text-muted">No project has a repository yet.</li>}
              </ul>
            </Card>
          </div>
        </div>
      )}
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Disconnect GitHub?"
        description="Fixify deletes the stored token and revokes its authorization on GitHub. Existing pull requests are not affected."
        footer={<><Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="danger" onClick={() => disconnect.mutate()} loading={disconnect.isPending}>Disconnect</Button></>}
      />
    </>
  );
}

export function GitHubCallbackPage() {
  const params = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const code = params.get("code");
    const state = params.get("state");
    const denied = params.get("error");
    if (denied || !code || !state) {
      setError(denied === "access_denied" ? "You declined the authorization on GitHub." : "GitHub did not return an authorization code.");
      return;
    }
    githubApi
      .complete(code, state)
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: ["github-status"] });
        router.replace("/github");
      })
      .catch((reason) => setError(errorText(reason)));
  }, [params, queryClient, router]);
  return (
    <Card className="mx-auto max-w-md p-6">
      {error ? (
        <div className="space-y-4">
          <Alert tone="error" title="GitHub could not be connected">{error}</Alert>
          <ButtonLink href="/github" variant="secondary">Back to GitHub settings</ButtonLink>
        </div>
      ) : (
        <p className="text-[13.5px] text-muted" role="status">Finishing the GitHub connection…</p>
      )}
    </Card>
  );
}
