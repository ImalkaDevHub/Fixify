"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, CheckCheck, GitPullRequest, Radar, ShieldAlert, Sparkles, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { notificationApi, type Notification } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { cn, safeInternalLink, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/overlays";
import { Card, CardHeader, EmptyState, PageHeader, Segmented, SkeletonRows } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

const ICONS: Record<string, typeof Bell> = {
  scan_started: Radar, scan_completed: Radar, scan_failed: XCircle, critical_findings: ShieldAlert, analysis_completed: Sparkles,
  fix_ready: Sparkles, fix_validation_failed: AlertTriangle, pull_request_created: GitPullRequest, job_failed: XCircle,
};
const TONE: Record<string, string> = { scan_failed: "text-critical", critical_findings: "text-critical", job_failed: "text-critical", fix_validation_failed: "text-warning", pull_request_created: "text-success" };

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const list = useQuery({ queryKey: ["notifications", "page", filter], queryFn: () => notificationApi.list(filter === "unread", 100), refetchInterval: 30_000 });
  const prefs = useQuery({ queryKey: ["notification-prefs"], queryFn: notificationApi.preferences });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });
  const readAll = useMutation({ mutationFn: notificationApi.readAll, onSuccess: () => void invalidate() });
  const save = useMutation({
    mutationFn: (changes: Record<string, boolean>) => notificationApi.savePreferences(changes),
    onSuccess: (data) => { queryClient.setQueryData(["notification-prefs"], data); toast.success("Preferences saved."); },
    onError: (e) => toast.error(errorText(e)),
  });
  const open = async (item: Notification) => {
    if (!item.read_at) await notificationApi.read(item.id).catch(() => undefined);
    void invalidate();
    const link = safeInternalLink(item.link);
    if (link) router.push(link);
  };

  return (
    <>
      <PageHeader eyebrow="Inbox" title="Notifications" description="Scan results, AI work, and pull requests." actions={<Button variant="secondary" onClick={() => readAll.mutate()} loading={readAll.isPending} disabled={!list.data?.unread_count}><CheckCheck className="h-4 w-4" /> Mark all as read</Button>} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="border-b border-line-soft px-5 py-3">
            <Segmented label="notification-filter" value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "unread", label: `Unread${list.data?.unread_count ? ` (${list.data.unread_count})` : ""}` }]} />
          </div>
          {list.isLoading ? (
            <SkeletonRows rows={5} />
          ) : !list.data?.items.length ? (
            <EmptyState icon={<Bell className="h-5 w-5" />} title="Nothing here" description="You will be notified when scans finish, AI work completes, or pull requests open." />
          ) : (
            <ul className="divide-y divide-line-soft">
              {list.data.items.map((item) => {
                const Icon = ICONS[item.kind] ?? Bell;
                return (
                  <li key={item.id}>
                    <button onClick={() => void open(item)} className={cn("flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors hover:bg-elevated/40", !item.read_at && "bg-violet/[0.04]")}>
                      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", TONE[item.kind] ?? "text-violet-soft")} aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13.5px] font-medium">{item.title}</span>
                        {item.body && <span className="block text-[12.5px] text-muted">{item.body}</span>}
                      </span>
                      <span className="shrink-0 text-[11.5px] text-subtle">{timeAgo(item.created_at)}</span>
                      {!item.read_at && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-violet" aria-label="Unread" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <Card className="h-fit">
          <CardHeader title="Preferences" description="Choose what creates an in-app notification." />
          <ul className="divide-y divide-line-soft">
            {prefs.data?.map((pref) => (
              <li key={pref.kind} className="flex items-center justify-between gap-3 px-5 py-3 text-[13px]">
                <span>{pref.label}</span>
                <Switch label={pref.label} checked={pref.enabled} disabled={save.isPending} onCheckedChange={(value) => save.mutate({ [pref.kind]: value })} />
              </li>
            ))}
            {prefs.isLoading && <SkeletonRows rows={4} />}
          </ul>
        </Card>
      </div>
    </>
  );
}
