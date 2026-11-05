"use client";

import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { motion } from "motion/react";
import { forwardRef, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, hover, ...props }: HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-card)] border border-line bg-card/90 shadow-[var(--shadow-card)]",
        hover && "transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-violet/40",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ title, description, action, className }: { title: ReactNode; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 border-b border-line-soft px-5 py-4", className)}>
      <div className="min-w-0">
        <h2 className="text-[14px] font-semibold tracking-tight text-ink">{title}</h2>
        {description && <p className="mt-0.5 text-[12.5px] text-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Entrance animation for cards and sections (disabled under reduced motion via MotionConfig). */
export function Reveal({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}

const badgeTones = {
  neutral: "border-line bg-elevated/70 text-muted",
  violet: "border-violet/30 bg-violet/10 text-violet-soft",
  cyan: "border-cyan/30 bg-cyan/10 text-cyan",
  success: "border-success/30 bg-success/10 text-success",
  warning: "border-warning/30 bg-warning/10 text-warning",
  critical: "border-critical/30 bg-critical/10 text-critical",
  high: "border-high/30 bg-high/10 text-high",
  low: "border-low/30 bg-low/10 text-low",
} as const;
export type BadgeTone = keyof typeof badgeTones;

export function Badge({ tone = "neutral", className, children, dot }: { tone?: BadgeTone; className?: string; children: ReactNode; dot?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium", badgeTones[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

export function Label({ htmlFor, children, hint }: { htmlFor?: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between gap-2 text-[12.5px] font-medium text-ink/90">
      <span>{children}</span>
      {hint && <span className="text-[11px] font-normal text-subtle">{hint}</span>}
    </label>
  );
}

const fieldClass =
  "w-full rounded-lg border border-line bg-panel/80 px-3 text-[13.5px] text-ink placeholder:text-subtle transition-colors focus:border-violet/70 focus:outline-none focus:ring-2 focus:ring-violet/20 disabled:opacity-60 aria-[invalid=true]:border-critical/70";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn(fieldClass, "h-10", className)} {...props} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn(fieldClass, "min-h-24 py-2.5", className)} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, ...props }, ref) {
  return <select ref={ref} className={cn(fieldClass, "h-10 appearance-none bg-[length:12px] pr-8", className)} {...props} />;
});

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1.5 text-[12px] text-critical">
      {message}
    </p>
  );
}

const alertTones = {
  info: { icon: Info, className: "border-cyan/25 bg-cyan/[0.06] text-cyan" },
  success: { icon: CheckCircle2, className: "border-success/25 bg-success/[0.06] text-success" },
  warning: { icon: AlertTriangle, className: "border-warning/25 bg-warning/[0.06] text-warning" },
  error: { icon: XCircle, className: "border-critical/25 bg-critical/[0.07] text-critical" },
};

export function Alert({ tone = "info", title, children, action, className }: { tone?: keyof typeof alertTones; title?: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  const { icon: Icon, className: toneClass } = alertTones[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex items-start gap-3 rounded-xl border px-4 py-3", toneClass, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 text-[13px] leading-relaxed">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-ink/75">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-md", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-5" aria-label="Loading" role="status">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className={cn("h-10", index % 2 ? "w-[92%]" : "w-full")} />
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-line bg-gradient-to-b from-elevated to-card text-violet-soft shadow-[var(--shadow-glow)]">
        {icon}
      </div>
      <h3 className="text-[14px] font-semibold">{title}</h3>
      <p className="mt-1.5 max-w-sm text-[13px] text-muted">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-violet-soft">{eyebrow}</p>}
        <h1 className="text-[24px] font-semibold tracking-tight text-ink sm:text-[26px]">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-[13.5px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, hint, icon, tone = "violet" }: { label: string; value: ReactNode; hint?: ReactNode; icon: ReactNode; tone?: "violet" | "cyan" | "critical" | "success" | "warning" }) {
  const toneClass = {
    violet: "text-violet-soft bg-violet/10 border-violet/20",
    cyan: "text-cyan bg-cyan/10 border-cyan/20",
    critical: "text-critical bg-critical/10 border-critical/20",
    success: "text-success bg-success/10 border-success/20",
    warning: "text-warning bg-warning/10 border-warning/20",
  }[tone];
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-medium text-muted">{label}</span>
        <span className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", toneClass)}>{icon}</span>
      </div>
      <div className="mt-3 text-[26px] font-semibold tracking-tight tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[11.5px] text-subtle">{hint}</div>}
    </Card>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (value: T) => void; options: { value: T; label: ReactNode }[]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-lg border border-line bg-panel/70 p-1">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "relative rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors",
              active ? "text-ink" : "text-muted hover:text-ink",
            )}
          >
            {active && <motion.span layoutId={`seg-${label}`} className="absolute inset-0 rounded-md border border-line bg-elevated" transition={{ type: "spring", duration: 0.35, bounce: 0.15 }} />}
            <span className="relative">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function KeyValue({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="divide-y divide-line-soft">
      {items.map((item) => (
        <div key={item.label} className="flex items-start justify-between gap-6 py-2.5 text-[13px]">
          <dt className="shrink-0 text-muted">{item.label}</dt>
          <dd className="min-w-0 break-words text-right text-ink/90">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
