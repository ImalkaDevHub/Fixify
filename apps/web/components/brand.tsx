import Link from "next/link";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex h-8 w-8 shrink-0 drop-shadow-[0_6px_16px_rgba(124,58,237,0.45)]", className)} aria-hidden>
      <svg viewBox="0 0 64 64" className="h-full w-full">
        <defs>
          <linearGradient id="fixify-mark-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#a78bfa" />
            <stop offset="1" stopColor="#6d28d9" />
          </linearGradient>
        </defs>
        <ellipse
          cx="32"
          cy="32"
          rx="27"
          ry="9"
          transform="rotate(-25 32 32)"
          fill="none"
          stroke="#c4b5fd"
          strokeWidth="3"
        />
        <rect x="14" y="14" width="36" height="36" rx="10" fill="url(#fixify-mark-g)" />
        <path
          d="M23 33l6 6 12-14"
          fill="none"
          stroke="#fff"
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="55.5" cy="21" r="3.4" fill="#ede9fe" />
      </svg>
    </span>
  );
}

export function Logo({ href = "/", compact = false }: { href?: string; compact?: boolean }) {
  return (
    <Link href={href} className="flex items-center gap-2.5" aria-label="Fixify home">
      <LogoMark />
      {!compact && <span className="text-[16px] font-semibold tracking-tight">Fixify</span>}
    </Link>
  );
}
