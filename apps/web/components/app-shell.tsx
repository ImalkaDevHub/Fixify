"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Bell,
  Bug,
  ChevronRight,
  ChevronsLeft,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Menu,
  Radar,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { authApi, notificationApi } from "@/lib/api";
import { errorText, useMe, useSignedOutRedirect } from "@/lib/hooks";
import { cn, initials, safeInternalLink, timeAgo } from "@/lib/utils";
import { Logo, LogoMark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger } from "@/components/ui/overlays";
import { Alert, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/scans", label: "Scans", icon: Radar },
  { href: "/findings", label: "Findings", icon: Bug },
  { href: "/fixes", label: "AI Fixes", icon: Sparkles },
  { href: "/github", label: "GitHub", icon: GitBranch },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings },
];

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Overview", projects: "Projects", new: "New project", scans: "Scans", findings: "Findings", fixes: "AI Fixes",
  github: "GitHub", callback: "Connecting", analytics: "Analytics", notifications: "Notifications", settings: "Settings",
};

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Breadcrumbs({ pathname }: { pathname: string }) {
  const segments = pathname.split("/").filter(Boolean);
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-[13px] text-muted md:flex">
      <Link href="/dashboard" className="hover:text-ink">Fixify</Link>
      {segments.map((segment, index) => {
        const href = "/" + segments.slice(0, index + 1).join("/");
        const label = SEGMENT_LABELS[segment] ?? "Details";
        const last = index === segments.length - 1;
        return (
          <span key={href} className="flex min-w-0 items-center gap-1.5">
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-subtle" aria-hidden />
            {last ? <span className="truncate text-ink" aria-current="page">{label}</span> : <Link href={href} className="truncate hover:text-ink">{label}</Link>}
          </span>
        );
      })}
    </nav>
  );
}

function NotificationsBell() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const { data } = useQuery({ queryKey: ["notifications", "bell"], queryFn: () => notificationApi.list(false, 8), refetchInterval: 30_000 });
  const readAll = useMutation({ mutationFn: notificationApi.readAll, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }) });
  const open = async (id: string, link: string | null) => {
    await notificationApi.read(id).catch(() => undefined);
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    const target = safeInternalLink(link);
    if (target) router.push(target);
  };
  const unread = data?.unread_count ?? 0;
  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <button className="relative flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-elevated hover:text-ink" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
          <Bell className="h-[18px] w-[18px]" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      </DropdownTrigger>
      <DropdownContent className="w-[min(360px,calc(100vw-1.5rem))] p-0">
        <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
          <span className="text-[13px] font-semibold">Notifications</span>
          {unread > 0 && (
            <button className="text-[12px] text-violet-soft hover:text-ink" onClick={() => readAll.mutate()}>
              Mark all as read
            </button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto scrollbar-thin">
          {!data?.items.length && <p className="px-4 py-8 text-center text-[13px] text-muted">You&apos;re all caught up.</p>}
          {data?.items.map((item) => (
            <DropdownItem key={item.id} onSelect={() => void open(item.id, item.link)}>
              <span className={cn("mt-1.5 h-2 w-2 shrink-0 self-start rounded-full", item.read_at ? "bg-transparent" : "bg-violet")} aria-hidden />
              <span className="min-w-0">
                <span className="block truncate font-medium">{item.title}</span>
                {item.body && <span className="line-clamp-2 block text-[12px] text-muted">{item.body}</span>}
                <span className="block text-[11px] text-subtle">{timeAgo(item.created_at)}</span>
              </span>
            </DropdownItem>
          ))}
        </div>
        <div className="border-t border-line-soft p-1.5">
          <DropdownItem onSelect={() => router.push("/notifications")}>View all notifications</DropdownItem>
        </div>
      </DropdownContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const { data: me } = useMe();
  const router = useRouter();
  const queryClient = useQueryClient();
  const signOut = async () => {
    await authApi.logout().catch(() => undefined);
    queryClient.clear();
    router.replace("/login");
  };
  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <button className="flex items-center gap-2 rounded-lg p-1 pr-2 hover:bg-elevated" aria-label="Account menu">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-violet/70 to-cyan/60 text-[11px] font-semibold">{me ? initials(me.display_name) : ""}</span>
          <span className="hidden max-w-32 truncate text-[13px] text-ink/90 sm:block">{me?.display_name}</span>
        </button>
      </DropdownTrigger>
      <DropdownContent>
        <div className="px-2.5 py-2">
          <p className="truncate text-[13px] font-medium">{me?.display_name}</p>
          <p className="truncate text-[12px] text-muted">{me?.email}</p>
        </div>
        <DropdownSeparator />
        <DropdownItem onSelect={() => router.push("/settings")}>
          <Settings className="h-4 w-4" /> Account settings
        </DropdownItem>
        <DropdownItem onSelect={() => void signOut()} danger>
          <LogOut className="h-4 w-4" /> Sign out
        </DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}

function VerifyBanner() {
  const { data: me } = useMe();
  const toast = useToast();
  const resend = useMutation({ mutationFn: authApi.resendVerification, onSuccess: (r) => toast.success(r.message), onError: (e) => toast.error(errorText(e)) });
  if (!me || me.email_verified) return null;
  return (
    <Alert
      tone="warning"
      className="mb-6"
      title="Verify your email address to start scanning"
      action={<Button size="sm" variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>Resend link</Button>}
    >
      We sent a link to {me.email}. Scans, AI analysis, and GitHub connections unlock after verification.
    </Alert>
  );
}

function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex h-9 items-center gap-3 rounded-lg px-2.5 text-[13px] font-medium transition-colors",
              active ? "text-ink" : "text-muted hover:bg-elevated/60 hover:text-ink",
              collapsed && "justify-center px-0",
            )}
          >
            {active && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-lg border border-violet/25 bg-gradient-to-r from-violet/20 to-violet/5" transition={{ type: "spring", duration: 0.4, bounce: 0.12 }} />}
            <Icon className={cn("relative h-[17px] w-[17px] shrink-0", active && "text-violet-soft")} aria-hidden />
            {!collapsed && <span className="relative truncate">{label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  useSignedOutRedirect();
  const pathname = usePathname();
  const { data: me, isLoading } = useMe();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setCollapsed(window.localStorage.getItem("fixify:sidebar") === "collapsed");
  }, []);
  const toggle = () => {
    setCollapsed((value) => {
      window.localStorage.setItem("fixify:sidebar", value ? "open" : "collapsed");
      return !value;
    });
  };

  return (
    <div className="ambient min-h-screen">
      <motion.aside
        animate={{ width: collapsed ? 72 : 244 }}
        transition={{ type: "spring", duration: 0.35, bounce: 0.1 }}
        className="fixed inset-y-0 left-0 z-30 hidden flex-col border-r border-line-soft bg-panel/80 px-3 py-4 backdrop-blur-xl lg:flex"
      >
        <div className={cn("mb-6 flex items-center px-1.5", collapsed ? "justify-center" : "justify-between")}>
          {collapsed ? <LogoMark /> : <Logo href="/dashboard" />}
        </div>
        <SidebarNav collapsed={collapsed} />
        <div className="mt-auto space-y-3">
          {!collapsed && (
            <div className="rounded-xl border border-line-soft bg-card/70 p-3 text-[12px] text-muted">
              <p className="font-medium text-ink/90">Humans stay in control</p>
              <p className="mt-1">AI proposes fixes; nothing reaches your repository until you approve it.</p>
            </div>
          )}
          <button onClick={toggle} className={cn("flex h-8 w-full items-center gap-2 rounded-lg px-2.5 text-[12px] text-muted hover:bg-elevated hover:text-ink", collapsed && "justify-center px-0")} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <ChevronsLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
            {!collapsed && "Collapse"}
          </button>
        </div>
      </motion.aside>

      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-black/60 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileOpen(false)} />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-panel px-3 py-4 lg:hidden"
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: "spring", duration: 0.35, bounce: 0.1 }}
              aria-label="Navigation"
            >
              <div className="mb-6 flex items-center justify-between px-1.5">
                <Logo href="/dashboard" />
                <button onClick={() => setMobileOpen(false)} className="rounded-md p-1.5 text-muted hover:bg-elevated" aria-label="Close navigation">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className={cn("transition-[padding] duration-300", collapsed ? "lg:pl-[72px]" : "lg:pl-[244px]")}>
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line-soft bg-canvas/75 px-4 backdrop-blur-xl sm:px-6">
          <button onClick={() => setMobileOpen(true)} className="rounded-md p-1.5 text-muted hover:bg-elevated hover:text-ink lg:hidden" aria-label="Open navigation">
            <Menu className="h-5 w-5" />
          </button>
          <div className="lg:hidden">
            <Logo href="/dashboard" compact />
          </div>
          <Breadcrumbs pathname={pathname} />
          <div className="ml-auto flex items-center gap-1.5">
            <NotificationsBell />
            {isLoading ? <Skeleton className="h-8 w-28" /> : <UserMenu />}
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-[1320px] px-4 py-7 sm:px-6 lg:px-8">
          {me && <VerifyBanner />}
          <AnimatePresence mode="wait">
            <motion.div key={pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
