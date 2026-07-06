import { useQuery } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { RwandaMap } from "@/components/RwandaMap";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { fetchOperationsSummary, fetchOperationsMap, fetchCentersLive } from "@/lib/api";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";
import type { OperationsSummary, CenterMapPoint, CenterLive } from "@/lib/types";
import {
  Building2, Wifi, WifiOff, CheckCircle2, XCircle,
  Database, Bell, ShieldAlert, Timer, Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";

const Stat = ({
  title, value, icon, tone = "default", hint,
}: {
  title: string; value: string | number; icon: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger"; hint?: string;
}) => {
  const toneMap = {
    default: "bg-card border",
    success: "border-success/30 bg-success/5",
    warning: "border-warning/30 bg-warning/5",
    danger: "border-destructive/30 bg-destructive/5",
  };
  const iconMap = {
    default: "bg-primary/10 text-primary",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    danger: "bg-destructive/15 text-destructive",
  };
  return (
    <div className={cn("rounded-2xl p-4 shadow-sm", toneMap[tone])}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className={cn("rounded-xl p-2", iconMap[tone])}>{icon}</div>
      </div>
    </div>
  );
};

const healthTone = (score: number) => {
  if (score >= 85) return "bg-success text-white";
  if (score >= 60) return "bg-warning text-black";
  if (score >= 30) return "bg-destructive text-white";
  return "bg-slate-800 text-white";
};

export default function OperationsCenter() {
  const { data: summary } = useQuery<OperationsSummary>({
    queryKey: ["operations", "summary"],
    queryFn: async () => (await fetchOperationsSummary()).data,
    ...LIVE_QUERY_OPTIONS,
  });

  const { data: points = [] } = useQuery<CenterMapPoint[]>({
    queryKey: ["operations", "map"],
    queryFn: async () => (await fetchOperationsMap()).data,
    ...LIVE_QUERY_OPTIONS,
  });

  const { data: centers = [] } = useQuery<CenterLive[]>({
    queryKey: ["centers", "live-ops"],
    queryFn: async () => (await fetchCentersLive()).data,
    ...LIVE_QUERY_OPTIONS,
  });

  const s = summary || ({} as OperationsSummary);

  const scored = [...centers]
    .map((c) => ({ ...c, score: Number(c.health_score ?? 0) }))
    .sort((a, b) => a.score - b.score);
  const worst = scored.slice(0, 6);

  const withCoords = points.filter((p) => p.latitude != null && p.longitude != null).length;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          title="Operations Center"
          subtitle="Single pane of glass — fleet status, replication threads, alerts, and health map."
        />

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat title="Total centers" value={s.total_centers ?? 0} icon={<Building2 className="h-5 w-5" />} />
          <Stat title="Online" value={s.online ?? 0} tone="success" icon={<Wifi className="h-5 w-5" />} />
          <Stat title="Offline" value={s.offline ?? 0} tone="danger" icon={<WifiOff className="h-5 w-5" />} />
          <Stat title="Databases monitored" value={s.databases_monitored ?? 0} icon={<Database className="h-5 w-5" />} />

          <Stat title="SQL running" value={s.sql_running ?? 0} tone="success" icon={<CheckCircle2 className="h-5 w-5" />} />
          <Stat title="SQL failed" value={s.sql_failed ?? 0} tone="danger" icon={<XCircle className="h-5 w-5" />} />
          <Stat title="IO running" value={s.io_running ?? 0} tone="success" icon={<CheckCircle2 className="h-5 w-5" />} />
          <Stat title="IO failed" value={s.io_failed ?? 0} tone="danger" icon={<XCircle className="h-5 w-5" />} />

          <Stat title="Alerts today" value={s.alerts_today ?? 0} tone="warning" icon={<Bell className="h-5 w-5" />} />
          <Stat title="Critical open" value={s.critical_open ?? 0} tone="danger" icon={<ShieldAlert className="h-5 w-5" />} />
          <Stat title="Avg replication lag" value={`${s.avg_replication_lag_seconds ?? 0}s`} icon={<Timer className="h-5 w-5" />} />
          <Stat
            title="Fleet health (avg)"
            value={
              centers.length
                ? Math.round(centers.reduce((a, c) => a + Number(c.health_score ?? 0), 0) / centers.length)
                : 0
            }
            icon={<Activity className="h-5 w-5" />}
          />
        </div>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Rwanda health map</CardTitle>
            <span className="text-xs text-muted-foreground">
              {withCoords}/{points.length} centers geolocated
            </span>
          </CardHeader>
          <CardContent>
            <RwandaMap points={points} />
            {withCoords === 0 && (
              <p className="mt-3 text-sm text-muted-foreground">
                No latitude/longitude set on any health center yet. Add coordinates in{" "}
                <Link className="underline" to="/health-centers/register">Register Health Center</Link>{" "}
                or edit an existing center.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Needs attention (lowest health score)</CardTitle>
          </CardHeader>
          <CardContent>
            {worst.length === 0 ? (
              <p className="text-sm text-muted-foreground">No health centers yet.</p>
            ) : (
              <ul className="divide-y">
                {worst.map((c) => (
                  <li key={c.center_id} className="flex items-center justify-between gap-4 py-3">
                    <div className="min-w-0 flex-1">
                      <Link to={`/health-centers/${c.center_id}`} className="font-medium hover:underline">
                        {c.name}
                      </Link>
                      <p className="truncate text-xs text-muted-foreground">
                        {c.district || "—"} · IO {c.replica_io || "?"} · SQL {c.replica_sql || "?"} · lag {c.seconds_behind ?? "?"}s
                      </p>
                    </div>
                    <div className="w-48">
                      <Progress value={c.score} className="h-2" />
                    </div>
                    <span className={cn("min-w-[3.5rem] rounded-md px-2 py-1 text-center text-xs font-semibold", healthTone(c.score))}>
                      {c.score}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
