"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Laptop, LogOut, Trash2, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { accountApi, aiApi } from "@/lib/api";
import { errorText, useMe } from "@/lib/hooks";
import { passwordSchema } from "@/lib/schemas";
import { formatDate, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/overlays";
import { Alert, Badge, Card, CardHeader, FieldError, Input, KeyValue, Label, PageHeader, SkeletonRows } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

function describeAgent(agent: string | null): string {
  if (!agent) return "Unknown device";
  const browser = /Edg\//.test(agent) ? "Edge" : /Chrome\//.test(agent) ? "Chrome" : /Firefox\//.test(agent) ? "Firefox" : /Safari\//.test(agent) ? "Safari" : "Browser";
  const os = /Windows/.test(agent) ? "Windows" : /Mac OS X/.test(agent) ? "macOS" : /Android/.test(agent) ? "Android" : /iPhone|iPad/.test(agent) ? "iOS" : /Linux/.test(agent) ? "Linux" : "";
  return os ? `${browser} on ${os}` : browser;
}

export function SettingsPage() {
  const { data: me } = useMe();
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [passwordError, setPasswordError] = useState<string | undefined>();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  useEffect(() => setName(me?.display_name ?? ""), [me?.display_name]);
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: accountApi.sessions });
  const ai = useQuery({ queryKey: ["ai-status"], queryFn: aiApi.status });

  const profile = useMutation({ mutationFn: () => accountApi.update(name), onSuccess: (user) => { queryClient.setQueryData(["me"], user); toast.success("Profile saved."); }, onError: (e) => toast.error(errorText(e)) });
  const password = useMutation({
    mutationFn: () => accountApi.changePassword(current, next),
    onSuccess: (r) => { setCurrent(""); setNext(""); toast.success(r.message); void queryClient.invalidateQueries({ queryKey: ["sessions"] }); },
    onError: (e) => setPasswordError(errorText(e)),
  });
  const revoke = useMutation({ mutationFn: (id: string) => accountApi.revokeSession(id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sessions"] }) });
  const revokeOthers = useMutation({ mutationFn: accountApi.revokeOthers, onSuccess: (r) => { toast.success(r.message); void queryClient.invalidateQueries({ queryKey: ["sessions"] }); } });
  const remove = useMutation({
    mutationFn: () => accountApi.remove(deletePassword),
    onSuccess: () => { queryClient.clear(); router.replace("/"); },
    onError: (e) => toast.error(errorText(e)),
  });

  const submitPassword = () => {
    const parsed = passwordSchema.safeParse(next);
    if (!parsed.success) {
      setPasswordError(parsed.error.issues[0]?.message);
      return;
    }
    setPasswordError(undefined);
    password.mutate();
  };

  return (
    <>
      <PageHeader eyebrow="Account" title="Settings" description="Profile, security, sessions, and data." />
      <div className="grid max-w-4xl gap-5">
        <Card>
          <CardHeader title={<span className="flex items-center gap-2"><UserRound className="h-4 w-4" /> Profile</span>} />
          <div className="grid gap-5 p-5 sm:grid-cols-2">
            <div>
              <Label htmlFor="name">Display name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={me?.email ?? ""} disabled />
              <p className="mt-1.5 text-[12px]">{me?.email_verified ? <Badge tone="success" dot>Verified</Badge> : <Badge tone="warning" dot>Not verified</Badge>}</p>
            </div>
          </div>
          <div className="flex justify-end border-t border-line-soft px-5 py-3">
            <Button onClick={() => profile.mutate()} loading={profile.isPending} disabled={!name.trim() || name === me?.display_name}>Save profile</Button>
          </div>
        </Card>

        <Card>
          <CardHeader title={<span className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Change password</span>} description="Every other session is signed out afterwards." />
          <div className="grid gap-5 p-5 sm:grid-cols-2">
            <div>
              <Label htmlFor="current">Current password</Label>
              <Input id="current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="new" hint="10+ characters">New password</Label>
              <Input id="new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
              <FieldError message={passwordError} />
            </div>
          </div>
          <div className="flex justify-end border-t border-line-soft px-5 py-3">
            <Button onClick={submitPassword} loading={password.isPending} disabled={!current || !next}>Change password</Button>
          </div>
        </Card>

        <Card>
          <CardHeader title={<span className="flex items-center gap-2"><Laptop className="h-4 w-4" /> Active sessions</span>} action={<Button size="sm" variant="secondary" onClick={() => revokeOthers.mutate()} loading={revokeOthers.isPending}><LogOut className="h-3.5 w-3.5" /> Sign out others</Button>} />
          {sessions.isLoading ? <SkeletonRows rows={2} /> : (
            <ul className="divide-y divide-line-soft">
              {sessions.data?.map((session) => (
                <li key={session.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-[13px]">
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{describeAgent(session.user_agent)} {session.current && <Badge tone="violet">This device</Badge>}</span>
                    <span className="block text-[12px] text-muted">{session.ip_address ?? "Unknown IP"} · last active {timeAgo(session.last_used_at)} · signed in {formatDate(session.created_at)}</span>
                  </span>
                  {!session.current && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(session.id)}>Sign out</Button>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title="Platform status" description="Read-only: configured by the server administrator." />
          <div className="px-5 py-2">
            <KeyValue items={[{ label: "AI analysis", value: ai.data?.available ? <Badge tone="success" dot>{ai.data.model}</Badge> : <Badge>Not configured</Badge> }]} />
          </div>
        </Card>

        <Card className="border-critical/30">
          <CardHeader title="Delete account" description="Permanently deletes your account, projects, scans, findings, screenshots, AI analyses, fix proposals, and the stored GitHub token." action={<Button variant="danger" onClick={() => setDeleteOpen(true)}><Trash2 className="h-4 w-4" /> Delete account</Button>} />
        </Card>
      </div>
      <Dialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete your account?"
        description="This cannot be undone. Pull requests already opened on GitHub stay there."
        footer={<><Button variant="ghost" onClick={() => setDeleteOpen(false)}>Cancel</Button><Button variant="danger" onClick={() => remove.mutate()} loading={remove.isPending} disabled={!deletePassword}>Delete permanently</Button></>}
      >
        <Alert tone="warning" className="mb-4">Enter your password to confirm.</Alert>
        <Label htmlFor="delete-password">Password</Label>
        <Input id="delete-password" type="password" autoComplete="current-password" value={deletePassword} onChange={(e) => setDeletePassword(e.target.value)} />
      </Dialog>
    </>
  );
}
