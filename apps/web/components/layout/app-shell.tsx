"use client";

import { usePathname } from "next/navigation";
import { Bell, Bug, CircleHelp, ClipboardList, FolderKanban, LayoutDashboard, Settings2 } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

const navigation = [
  { label: "Overview", href: "/", icon: LayoutDashboard, active: (path: string) => path === "/" || path === "/dashboard" },
  { label: "Projects", href: "/projects", icon: FolderKanban, active: (path: string) => ["/projects", "/scans", "/findings"].some((prefix) => path.startsWith(prefix)) },
];
const futureNavigation = [
  { label: "All test runs", icon: ClipboardList },
  { label: "All findings", icon: Bug },
  { label: "Settings", icon: Settings2 },
];

function titleFor(pathname: string): string {
  if (pathname.startsWith("/scans/")) return "Scan report";
  if (pathname.startsWith("/findings/")) return "Finding";
  if (pathname.startsWith("/projects/new")) return "New project";
  if (pathname.startsWith("/projects/")) return "Project details";
  if (pathname.startsWith("/projects")) return "Projects";
  return "Overview";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const pageTitle = titleFor(pathname);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Link href="/" className="brand" aria-label="Fixify overview">
          <span className="brand-mark"><Bug size={19} strokeWidth={2.2} /></span>
          <span>
            <span className="brand-name">Fixify</span>
            <span className="brand-caption">Website quality</span>
          </span>
        </Link>
        <p className="nav-label">Workspace</p>
        <nav className="nav-list">
          {navigation.map(({ label, href, icon: Icon, active }) => (
            <Link key={label} href={href} className={`nav-link${active(pathname) ? " active" : ""}`}>
              <Icon size={17} strokeWidth={1.8} />{label}
            </Link>
          ))}
        </nav>
        <p className="nav-label">Monitor</p>
        <nav className="nav-list" aria-label="Coming soon">
          {futureNavigation.map(({ label, icon: Icon }) => (
            <span key={label} className="nav-link disabled" aria-disabled="true" title="Coming soon">
              <Icon size={17} strokeWidth={1.8} />{label}<span className="nav-soon">SOON</span>
            </span>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="nav-link disabled" aria-disabled="true"><CircleHelp size={17} />Help center</span>
          <div className="sidebar-note">
            <strong>Just getting started?</strong>
            Add a website, then run a scan from its project page. Only scan sites you are authorized to test.
          </div>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <span className="topbar-title">{pageTitle}</span>
          <div className="topbar-actions">
            <button className="icon-button" aria-label="Notifications" title="No new notifications">
              <Bell size={17} />
            </button>
            <span className="avatar" aria-label="Local development workspace">FX</span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
