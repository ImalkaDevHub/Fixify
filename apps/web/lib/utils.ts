import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Parse an API timestamp. Values without a zone (SQLite in tests) are UTC, like everything the
 * API stores; treating them as local time would shift them by the browser's offset.
 */
export function parseTimestamp(value: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) || !value.includes("T") ? value : `${value}Z`);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(parseTimestamp(value));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(parseTimestamp(value));
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "never";
  const seconds = Math.round((Date.now() - parseTimestamp(value).getTime()) / 1000);
  if (seconds < 0) {
    const ahead = -seconds;
    if (ahead < 3600) return `in ${Math.max(1, Math.round(ahead / 60))} min`;
    if (ahead < 86_400) return `in ${Math.round(ahead / 3600)} h`;
    return `in ${Math.round(ahead / 86_400)} d`;
  }
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h ago`;
  if (seconds < 30 * 86_400) return `${Math.round(seconds / 86_400)} d ago`;
  return formatDate(value);
}

export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined) return "—";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  const seconds = Math.round(milliseconds / 100) / 10;
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function hostname(value: string): string {
  try {
    return new URL(value).hostname;
  } catch {
    return value;
  }
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? "?").slice(0, 2)).toUpperCase();
}

export function humanize(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Only same-site relative links from notifications; anything else is ignored. */
export function safeInternalLink(link: string | null | undefined): string | null {
  return link && link.startsWith("/") && !link.startsWith("//") ? link : null;
}
