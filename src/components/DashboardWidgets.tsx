import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: "online" | "offline" | "partial";
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const styles = {
    online: "bg-success/15 text-success border-success/30",
    offline: "bg-destructive/15 text-destructive border-destructive/30",
    partial: "bg-warning/15 text-warning border-warning/30",
  };
  const labels = { online: "Online", offline: "Offline", partial: "Partial" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border", styles[status], className)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", {
        "bg-success": status === "online",
        "bg-destructive": status === "offline",
        "bg-warning": status === "partial",
      })} />
      {labels[status]}
    </span>
  );
}

interface SummaryCardProps {
  title: string;
  value: string | number;
  icon: ReactNode;
  trend?: string;
  className?: string;
}

export function SummaryCard({ title, value, icon, trend, className }: SummaryCardProps) {
  return (
    <div className={cn("bg-card rounded-xl border p-5 shadow-sm card-lift animate-fade-in-up", className)}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-bold mt-1 text-card-foreground tabular-nums">{value}</p>
          {trend && <p className="text-xs text-muted-foreground mt-1">{trend}</p>}
        </div>
        <div className="w-10 h-10 rounded-lg gradient-primary flex items-center justify-center text-primary-foreground shadow-md shadow-primary/20">
          {icon}
        </div>
      </div>
    </div>
  );
}

export function RiskBadge({ score }: { score: number }) {
  const color = score >= 60 ? "text-destructive" : score >= 30 ? "text-warning" : "text-success";
  const bg = score >= 60 ? "bg-destructive/10" : score >= 30 ? "bg-warning/10" : "bg-success/10";
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-bold", color, bg)}>
      {score}%
    </span>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
