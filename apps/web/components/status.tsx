import type { FixStatus, JobStatus, RunStatus, Severity } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge, type BadgeTone } from "@/components/ui/primitives";

export const SEVERITY_TONE: Record<Severity, BadgeTone> = { critical: "critical", high: "high", medium: "warning", low: "low", info: "neutral" };
export const SEVERITY_COLOR: Record<Severity, string> = { critical: "#FB7185", high: "#FB923C", medium: "#FBBF24", low: "#38BDF8", info: "#64748B" };

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge tone={SEVERITY_TONE[severity]} dot className="capitalize">
      {severity}
    </Badge>
  );
}

const RUN: Record<RunStatus, { tone: BadgeTone; label: string }> = {
  queued: { tone: "violet", label: "Queued" },
  running: { tone: "cyan", label: "Running" },
  completed: { tone: "success", label: "Completed" },
  completed_with_errors: { tone: "warning", label: "Completed with errors" },
  failed: { tone: "critical", label: "Failed" },
  cancelled: { tone: "neutral", label: "Cancelled" },
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const { tone, label } = RUN[status];
  return (
    <Badge tone={tone}>
      {(status === "running" || status === "queued") && <span className={cn("h-1.5 w-1.5 rounded-full bg-current", status === "running" && "animate-pulse")} />}
      {label}
    </Badge>
  );
}

const FIX: Record<FixStatus, { tone: BadgeTone; label: string }> = {
  pending_review: { tone: "violet", label: "Pending review" },
  approved: { tone: "cyan", label: "Approved" },
  rejected: { tone: "neutral", label: "Rejected" },
  applied: { tone: "success", label: "Applied" },
  failed_validation: { tone: "critical", label: "Failed validation" },
  superseded: { tone: "neutral", label: "Superseded" },
};

export function FixStatusBadge({ status }: { status: FixStatus }) {
  return <Badge tone={FIX[status].tone}>{FIX[status].label}</Badge>;
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const tone: BadgeTone = { queued: "violet", running: "cyan", succeeded: "success", failed: "critical", cancelled: "neutral" }[status] as BadgeTone;
  return <Badge tone={tone}>{status === "running" ? "Working" : status.charAt(0).toUpperCase() + status.slice(1)}</Badge>;
}

export function ConfidenceBadge({ value }: { value: string }) {
  const tone: BadgeTone = value === "confirmed" || value === "high" ? "success" : value === "medium" ? "cyan" : "neutral";
  return <Badge tone={tone} className="capitalize">{value === "suspected" ? "Suspected" : value === "confirmed" ? "Confirmed" : `${value} confidence`}</Badge>;
}

export function ValidationBadge({ value }: { value: "passed" | "failed" | "not_available" }) {
  const map = { passed: ["success", "Validation passed"], failed: ["critical", "Validation failed"], not_available: ["neutral", "No syntax check"] } as const;
  return <Badge tone={map[value][0]}>{map[value][1]}</Badge>;
}

/** Compact stacked bar of severity counts. */
export function SeverityBar({ counts, className }: { counts: Record<Severity, number>; className?: string }) {
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  if (!total) return <div className={cn("h-1.5 rounded-full bg-success/40", className)} title="No findings" />;
  return (
    <div className={cn("flex h-1.5 overflow-hidden rounded-full bg-elevated", className)} title={`${total} findings`}>
      {(Object.keys(SEVERITY_COLOR) as Severity[]).map((severity) =>
        counts[severity] ? <span key={severity} style={{ width: `${(counts[severity] / total) * 100}%`, background: SEVERITY_COLOR[severity] }} /> : null,
      )}
    </div>
  );
}

export function SeverityCounts({ counts }: { counts: Record<Severity, number> }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {(Object.keys(SEVERITY_COLOR) as Severity[]).map((severity) => (
        <li key={severity} className={cn("flex items-center gap-1.5 rounded-md border border-line-soft bg-panel/70 px-2 py-1 text-[11.5px] capitalize", !counts[severity] && "opacity-45")}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[severity] }} />
          <span className="text-muted">{severity}</span>
          <span className="font-semibold tabular-nums text-ink">{counts[severity]}</span>
        </li>
      ))}
    </ul>
  );
}
