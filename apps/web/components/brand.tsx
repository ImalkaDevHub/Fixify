import Link from "next/link";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("relative flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-violet to-cyan shadow-[0_6px_20px_-6px_rgba(139,92,246,0.8)]", className)} aria-hidden>
      <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 13l4 4L19 7" />
        <path d="M5 7h6" opacity="0.6" />
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
