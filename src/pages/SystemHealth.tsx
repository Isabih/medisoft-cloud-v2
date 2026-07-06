import { useQuery } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchSystemHealthCheck, API_BASE_URL } from "@/lib/api";
import { CheckCircle2, XCircle, RefreshCw, Activity } from "lucide-react";

type CheckResult = { ok: boolean; [k: string]: any };
type Report = {
  ok: boolean;
  checked_at: string;
  api_prefix: string;
  checks: Record<string, CheckResult>;
};

const LABELS: Record<string, string> = {
  database: "Database connectivity",
  routes: "Backend API routes",
  websocket: "WebSocket (/ws/monitor)",
  agent_control: "Agent control queue",
  audit_log: "Audit log table",
  sms_logs: "SMS log table",
  sms_config: "SMS gateway config",
};

function StatusRow({ name, result }: { name: string; result: CheckResult }) {
  const ok = !!result.ok;
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <div className="flex items-start gap-3 min-w-0">
        {ok ? (
          <CheckCircle2 className="w-5 h-5 text-success mt-0.5 shrink-0" />
        ) : (
          <XCircle className="w-5 h-5 text-destructive mt-0.5 shrink-0" />
        )}
        <div className="min-w-0">
          <p className="font-medium text-sm">{LABELS[name] || name}</p>
          <pre className="text-[11px] text-muted-foreground mt-1 whitespace-pre-wrap break-all">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      </div>
      <Badge variant={ok ? "default" : "destructive"} className="shrink-0">
        {ok ? "OK" : "FAIL"}
      </Badge>
    </div>
  );
}

export default function SystemHealthPage() {
  const { data, isFetching, refetch, error } = useQuery({
    queryKey: ["system-health-check"],
    queryFn: async () => (await fetchSystemHealthCheck()).data as Report,
    refetchOnWindowFocus: false,
  });

  return (
    <DashboardLayout>
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Activity className="w-6 h-6 text-primary" />
              System Health Check
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Verifies backend routes, WebSocket, and agent control connectivity after installation.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              API base URL: <code className="bg-muted px-1 rounded">{API_BASE_URL}</code>
            </p>
          </div>
          <Button onClick={() => refetch()} disabled={isFetching} variant="outline">
            <RefreshCw className={`w-4 h-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
            Re-run checks
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Overall status</span>
              {data && (
                <Badge variant={data.ok ? "default" : "destructive"}>
                  {data.ok ? "All systems operational" : "Issues detected"}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {error && (
              <p className="text-sm text-destructive">
                Could not reach backend. Check that FastAPI is running and the API base URL is correct.
              </p>
            )}
            {!data && !error && <p className="text-sm text-muted-foreground">Running checks…</p>}
            {data && (
              <div>
                {Object.entries(data.checks).map(([name, result]) => (
                  <StatusRow key={name} name={name} result={result} />
                ))}
                <p className="text-xs text-muted-foreground mt-3">
                  Last checked: {new Date(data.checked_at).toLocaleString()}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
