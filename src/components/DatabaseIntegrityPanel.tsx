import { useQuery } from "@tanstack/react-query";
import { fetchDatabaseIntegritySummary, fetchCentersLive } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Database, ShieldCheck, AlertTriangle } from "lucide-react";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";

export function DatabaseIntegrityPanel() {
  const { data } = useQuery({
    queryKey: ["database-integrity-summary"],
    queryFn: async () => (await fetchDatabaseIntegritySummary()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 60000,
  });

  const { data: liveCenters } = useQuery({
    queryKey: ["centers-live"],
    queryFn: async () => (await fetchCentersLive()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 60000,
  });
  const centers = Array.isArray(liveCenters) ? liveCenters : [];
  const score = Number(data?.average_data_health_score ?? 0);
  const status = score >= 90 ? "Healthy" : score >= 70 ? "Minor Drift" : score >= 40 ? "Major Drift" : "Critical Drift";

  return (
    <Card className="rounded-2xl shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Database className="h-4 w-4 text-primary" />
          Database Integrity & Drift
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-2xl font-bold">{score.toFixed(1)}%</p>
            <p className="text-xs text-muted-foreground">Local vs cloud data match score</p>
          </div>
          <Badge variant={score >= 90 ? "secondary" : "destructive"} className="gap-1">
            {score >= 90 ? <ShieldCheck className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
            {status}
          </Badge>
        </div>
        <Progress value={score} className="h-2" />
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-xl border p-3"><p className="text-muted-foreground">Databases</p><p className="font-bold">{data?.total_databases ?? 0}</p></div>
          <div className="rounded-xl border p-3"><p className="text-muted-foreground">Drifting</p><p className="font-bold text-warning">{data?.drifting ?? 0}</p></div>
          <div className="rounded-xl border p-3"><p className="text-muted-foreground">Healthy</p><p className="font-bold text-success">{data?.healthy ?? 0}</p></div>
          <div className="rounded-xl border p-3"><p className="text-muted-foreground">Critical</p><p className="font-bold text-destructive">{data?.critical_drift ?? 0}</p></div>
        </div>
        <div className="border-t pt-3 space-y-3">
          <p className="font-semibold text-sm">Orders-only verification & server clocks</p>
          <p className="text-xs text-muted-foreground">Read-only schema inspection every 60 seconds. Counts remain unverified until the local agent reports orders at a matching replication checkpoint.</p>
          {centers.map((center: any) => {
            const d = center.orders_diagnostics;
            if (!d) return null;
            return <div key={center.foss_id} className="rounded-xl border p-3 space-y-2 text-xs">
              <div className="flex justify-between gap-2"><strong>{center.name || center.foss_id}</strong><Badge variant={d.schema_exists ? "secondary" : "destructive"}>{d.schema_exists ? "orders schema found" : "orders unavailable"}</Badge></div>
              <p>Cloud MySQL time: {d.cloud_time_local || "Unknown"} ({d.cloud_mysql_timezone || "timezone unknown"})</p>
              <p>Cloud UTC: {d.cloud_time_utc || "Unknown"}</p>
              <p>Local agent reported time: {d.local_agent_reported_time || "Unknown"}</p>
              <p>Clock difference: Not verified (requires an agent-side UTC clock sample)</p>
              <p>Orders columns: {d.columns?.map((c: any) => c.name).join(", ") || "Unavailable"}</p>
              <p>Orders indexes: {d.indexes?.map((x: any) => x.name + ":" + x.column_name).join(", ") || "Unavailable"}</p>
              <p>Replica lag: {d.replication_lag_seconds == null ? "Unknown" : d.replication_lag_seconds + " seconds"}</p>
              <p className="text-amber-700 dark:text-amber-400">Why: {d.lag_reason}</p>
              <p>Orders comparison: {d.comparison_reason}</p>
              {center.io_diagnostics?.reason && <p>IO diagnosis: {center.io_diagnostics.reason}</p>}
              {center.io_diagnostics?.suggested_solution && <p>Suggested action: {center.io_diagnostics.suggested_solution}</p>}
            </div>;
          })}
          {!centers.length && <p className="text-xs text-muted-foreground">No live center reports available.</p>}
        </div>
      </CardContent>
    </Card>
  );
}
