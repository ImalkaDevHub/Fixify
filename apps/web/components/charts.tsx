"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyPoint, Severity } from "@/lib/api";
import { SEVERITY_COLOR } from "@/components/status";

const AXIS = { stroke: "#475569", fontSize: 11, tickLine: false, axisLine: false } as const;
const GRID = { stroke: "#1C2639", strokeDasharray: "3 6", vertical: false } as const;

function shortDate(value: string) {
  const date = new Date(`${value}T00:00:00Z`);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" }).format(date);
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-card/95 px-3 py-2 text-[12px] shadow-xl backdrop-blur">
      {label && <p className="mb-1 font-medium text-ink">{/^\d{4}-\d{2}-\d{2}$/.test(label) ? shortDate(label) : label}</p>}
      {payload.map((item) => (
        <p key={item.name} className="flex items-center gap-2 text-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
          {item.name}: <span className="font-semibold tabular-nums text-ink">{item.value}</span>
        </p>
      ))}
    </div>
  );
}

export function ScanActivityChart({ data }: { data: DailyPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="scans-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8B5CF6" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#8B5CF6" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="failed-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FB7185" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#FB7185" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={24} />
        <YAxis allowDecimals={false} {...AXIS} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#263249" }} />
        <Area type="monotone" dataKey="scans" name="Scans" stroke="#8B5CF6" strokeWidth={2} fill="url(#scans-fill)" />
        <Area type="monotone" dataKey="failed_scans" name="Failed" stroke="#FB7185" strokeWidth={1.5} fill="url(#failed-fill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SeverityDonut({ counts }: { counts: Record<Severity, number> }) {
  const data = (Object.keys(SEVERITY_COLOR) as Severity[]).map((severity) => ({ name: severity, value: counts[severity] })).filter((item) => item.value > 0);
  const total = data.reduce((sum, item) => sum + item.value, 0);
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={62} outerRadius={88} paddingAngle={data.length > 1 ? 3 : 0} stroke="none">
            {data.map((item) => (
              <Cell key={item.name} fill={SEVERITY_COLOR[item.name as Severity]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[26px] font-semibold tabular-nums">{total}</span>
        <span className="text-[11px] text-muted">current findings</span>
      </div>
    </div>
  );
}

export function SeverityOverTimeChart({ data }: { data: DailyPoint[] }) {
  const rows = data.map((point) => ({ date: point.date, ...point.severity }));
  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={rows} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={24} />
        <YAxis allowDecimals={false} {...AXIS} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(139,92,246,0.06)" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#94A3B8" }} iconType="circle" iconSize={7} />
        {(["critical", "high", "medium", "low", "info"] as Severity[]).map((severity) => (
          <Bar key={severity} dataKey={severity} name={severity} stackId="s" fill={SEVERITY_COLOR[severity]} radius={severity === "info" ? [3, 3, 0, 0] : 0} maxBarSize={28} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function NewResolvedChart({ data }: { data: DailyPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={24} />
        <YAxis allowDecimals={false} {...AXIS} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(34,211,238,0.05)" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#94A3B8" }} iconType="circle" iconSize={7} />
        <Bar dataKey="new_findings" name="New" fill="#FB7185" radius={[3, 3, 0, 0]} maxBarSize={18} />
        <Bar dataKey="resolved_findings" name="Resolved" fill="#34D399" radius={[3, 3, 0, 0]} maxBarSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function HealthTrendChart({ data }: { data: DailyPoint[] }) {
  const rows = data.filter((point) => point.health !== null);
  return (
    <ResponsiveContainer width="100%" height={250}>
      <LineChart data={rows} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="health-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#8B5CF6" />
            <stop offset="100%" stopColor="#22D3EE" />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} minTickGap={24} />
        <YAxis domain={[0, 100]} {...AXIS} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#263249" }} />
        <Line type="monotone" dataKey="health" name="Health" stroke="url(#health-line)" strokeWidth={2.5} dot={{ r: 2.5, fill: "#22D3EE", strokeWidth: 0 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ChartEmpty({ children }: { children: React.ReactNode }) {
  return <div className="flex h-[220px] items-center justify-center rounded-lg border border-dashed border-line text-center text-[13px] text-muted">{children}</div>;
}
