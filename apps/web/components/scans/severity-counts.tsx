import { SEVERITIES, type Severity } from "@/lib/api";

export function SeverityCounts({ counts }: { counts: Record<Severity, number> }) {
  return (
    <ul className="severity-counts" aria-label="Findings by severity">
      {SEVERITIES.map((severity) => (
        <li key={severity} className={`severity-count severity-${severity}${counts[severity] ? "" : " is-zero"}`}>
          <span className="severity-count-value">{counts[severity]}</span>
          <span className="severity-count-label">{severity}</span>
        </li>
      ))}
    </ul>
  );
}
