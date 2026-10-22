import type { CheckStatus, RunStatus, Severity } from "@/lib/api";

const RUN_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  completed_with_errors: "Completed with errors",
  failed: "Failed",
  cancelled: "Cancelled",
};

const CHECK_LABELS: Record<CheckStatus, string> = {
  passed: "Passed",
  failed: "Issues found",
  skipped: "Skipped",
  error: "Could not run",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <span className={`badge run-${status}`}>{RUN_LABELS[status]}</span>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`badge severity-${severity}`}>{severity}</span>;
}

export function CheckStatusBadge({ status }: { status: CheckStatus }) {
  return <span className={`badge check-${status}`}>{CHECK_LABELS[status]}</span>;
}

export function ConfidenceBadge({ confidence }: { confidence: "confirmed" | "suspected" }) {
  return (
    <span className={`badge confidence-${confidence}`} title={confidence === "confirmed"
      ? "Observed directly during the scan"
      : "Observed, but could be temporary or caused by the scanner being blocked"}>
      {confidence === "confirmed" ? "Observed" : "Suspected"}
    </span>
  );
}
