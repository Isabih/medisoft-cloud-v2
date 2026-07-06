import { useQuery } from "@tanstack/react-query";
import { fetchDatabaseIntegritySummary } from "@/lib/api";
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
      </CardContent>
    </Card>
  );
}
