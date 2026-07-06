import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";

import { useState } from "react";
import {
  ArrowLeft, Activity, Server, RefreshCw, RotateCcw, Power,
  AlertTriangle, CheckCircle2, XCircle, Loader2, MessageSquare,
} from "lucide-react";
import { toast } from "sonner";

import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AutoHealButton } from "@/components/AutoHealButton";
import { AiDiagnosePanel } from "@/components/AiDiagnosePanel";
import { HeartbeatTimeline } from "@/components/HeartbeatTimeline";

import api, { fetchHealthCenter, fetchSmsLogs } from "@/lib/api";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";
import { cn } from "@/lib/utils";

type SourceReport = {
  foss_id: string;
  health_center_name: string | null;
  db_name: string | null;
  channel_name: string | null;
  hostname: string | null;
  mysql_status: string | null;
  internet_status: string | null;
  cloud_connection: string | null;
  vpn_status: string | null;
  cpu_usage: number;
  ram_usage: number;
  disk_usage: number;
  database_size_mb: number;
  io_running: string | null;
  sql_running: string | null;
  connected_replicas: number;
  replica_hosts: string | null;
  local_row_count: number;
  local_latest_time: string | null;
  sent_at: string | null;
  received_at: string;
};

type AgentAction = {
  id: number;
  action: string;
  params: string | null;
  status: "pending" | "dispatched" | "done" | "failed";
  requested_by: string | null;
  created_at: string;
  dispatched_at: string | null;
  result: string | null;
};

const StatusPill = ({ ok, label }: { ok: boolean; label: string }) => (
  <Badge variant={ok ? "default" : "destructive"} className="gap-1">
    {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
    {label}
  </Badge>
);

const Gauge = ({ label, value }: { label: string; value: number }) => {
  const v = Math.min(100, Math.max(0, Number(value) || 0));
  const color = v > 90 ? "text-destructive" : v > 75 ? "text-warning" : "text-success";
  return (
    <div className="rounded-xl border bg-card p-4 card-lift">
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-3xl font-bold font-mono", color)}>{v.toFixed(0)}%</p>
      <Progress value={v} className="mt-3 h-1.5" />
    </div>
  );
};

export default function HealthCenterDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);

  const { data: hc } = useQuery({
    queryKey: ["health-center", id],
    queryFn: async () => (await fetchHealthCenter(id!)).data,
    enabled: !!id,
  });

  const fossId: string | undefined = hc?.foss_id;

  const { data: report, isPending: loadingReport, refetch: refetchReport } =
    useQuery<SourceReport | null>({
      queryKey: ["source-report", fossId],
      queryFn: async () =>
        (await api.get(`/hybrid/source-reports/${fossId}`)).data,
      enabled: !!fossId,
      ...LIVE_QUERY_OPTIONS,
      refetchInterval: 15000,
    });

  const { data: actions = [], refetch: refetchActions } = useQuery<AgentAction[]>({
    queryKey: ["agent-actions", fossId],
    queryFn: async () => (await api.get(`/agent/${fossId}/actions`)).data,
    enabled: !!fossId,
    refetchInterval: 15000,
  });

  const { data: smsLogs = [] } = useQuery({
    queryKey: ["sms-logs", id],
    queryFn: async () => (await fetchSmsLogs({ center_id: id })).data,
    enabled: !!id,
    refetchInterval: 30000,
  });

  const runAction = useMutation({
    mutationFn: async (action: string) => {
      if (!fossId) throw new Error("No FOSS ID for this center");
      setBusy(action);
      return (await api.post(`/agent/${fossId}/${action}`, { requested_by: "admin" })).data;
    },
    onSuccess: (_, action) => {
      toast.success(`${action} queued — agent will pick it up on next poll`);
      refetchActions();
      setBusy(null);
    },
    onError: (e: any) => {
      toast.error(e?.response?.data?.detail || e?.message || "Action failed");
      setBusy(null);
    },
  });

  if (!hc) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  const ioOk = (report?.io_running || "").toLowerCase() === "yes";
  const sqlOk = (report?.sql_running || "").toLowerCase() === "yes";
  const lastSeen = report?.received_at ? new Date(report.received_at) : null;
  const ageMin = lastSeen ? Math.floor((Date.now() - lastSeen.getTime()) / 60000) : null;
  const online = ageMin !== null && ageMin < 3;

  return (
    <DashboardLayout>
      <div className="space-y-6 page-enter">
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>

        <PageHeader
          title={hc.name || "Health Center"}
          subtitle={`FOSS ID ${hc.foss_id} · ${hc.province || "—"} / ${hc.district || "—"}`}
        />

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={online ? "default" : "destructive"} className="gap-1">
            <span className={cn("inline-block h-2 w-2 rounded-full", online ? "bg-success animate-pulse" : "bg-destructive")} />
            {online ? `Online · ${ageMin}m ago` : ageMin === null ? "No telemetry yet" : `Offline · ${ageMin}m`}
          </Badge>
          {report && <StatusPill ok={ioOk} label={`IO ${report.io_running || "?"}`} />}
          {report && <StatusPill ok={sqlOk} label={`SQL ${report.sql_running || "?"}`} />}
          {report?.vpn_status && (
            <Badge variant="outline">VPN {report.vpn_status}</Badge>
          )}
        </div>

        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="resources">Resources</TabsTrigger>
            <TabsTrigger value="actions">Actions</TabsTrigger>
            <TabsTrigger value="sms">SMS</TabsTrigger>
            <TabsTrigger value="ai">AI Diagnose</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Server className="h-4 w-4 text-primary" /> Live snapshot
                </CardTitle>
              </CardHeader>
              <CardContent>
                {loadingReport && !report ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" /> Waiting for first agent push…
                  </div>
                ) : !report ? (
                  <div className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="mt-0.5 h-4 w-4 text-warning" />
                    No telemetry received yet. Install the Local Agent on this
                    server (see the Installers page).
                  </div>
                ) : (
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
                    <Row k="Hostname" v={report.hostname} />
                    <Row k="Database" v={report.db_name} />
                    <Row k="Channel" v={report.channel_name} />
                    <Row k="MySQL" v={report.mysql_status} />
                    <Row k="Internet" v={report.internet_status} />
                    <Row k="Cloud link" v={report.cloud_connection} />
                    <Row k="Connected replicas" v={String(report.connected_replicas)} />
                    <Row k="Local rows" v={report.local_row_count?.toLocaleString()} />
                    <Row k="DB size" v={`${report.database_size_mb} MB`} />
                    <Row k="Last sent" v={report.sent_at} />
                    <Row k="Last received" v={report.received_at} />
                  </dl>
                )}
              </CardContent>
            </Card>

            <HeartbeatTimeline centerId={id!} hours={24} />
          </TabsContent>


          <TabsContent value="resources" className="space-y-4">
            {!report ? (
              <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">No data yet.</CardContent></Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-3">
                <Gauge label="CPU" value={report.cpu_usage} />
                <Gauge label="RAM" value={report.ram_usage} />
                <Gauge label="Disk" value={report.disk_usage} />
              </div>
            )}
          </TabsContent>

          <TabsContent value="actions" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Remote control</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  Each command is queued and picked up by the local agent on its
                  next 30-second poll. The agent uses the auto-heal hook in the
                  installed script.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" disabled={!fossId || busy === "restart-mysql"} onClick={() => runAction.mutate("restart-mysql")}>
                    <Power className="mr-2 h-3.5 w-3.5" /> Restart MySQL
                  </Button>
                  <Button size="sm" variant="outline" disabled={!fossId || busy === "restart-replica"} onClick={() => runAction.mutate("restart-replica")}>
                    <RefreshCw className="mr-2 h-3.5 w-3.5" /> Restart Replica
                  </Button>
                  <Button size="sm" variant="outline" disabled={!fossId || busy === "reset-replica"} onClick={() => runAction.mutate("reset-replica")}>
                    <RotateCcw className="mr-2 h-3.5 w-3.5" /> Reset Replica
                  </Button>
                  <Button size="sm" variant="outline" disabled={!fossId || busy === "start-replica"} onClick={() => runAction.mutate("start-replica")}>
                    Start Replica
                  </Button>
                  <Button size="sm" variant="outline" disabled={!fossId || busy === "stop-replica"} onClick={() => runAction.mutate("stop-replica")}>
                    Stop Replica
                  </Button>
                  {hc.replication_channel && (
                    <AutoHealButton channelName={hc.replication_channel} />
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Recent commands</CardTitle>
              </CardHeader>
              <CardContent>
                {actions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No commands queued yet.</p>
                ) : (
                  <div className="space-y-2">
                    {actions.map((a) => (
                      <div key={a.id} className="flex items-center justify-between rounded-lg border p-2 text-xs">
                        <div className="font-mono">{a.action}</div>
                        <div className="text-muted-foreground">{new Date(a.created_at).toLocaleString()}</div>
                        <Badge variant={a.status === "done" ? "default" : a.status === "failed" ? "destructive" : "outline"}>
                          {a.status}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="sms">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <MessageSquare className="h-4 w-4 text-primary" /> SMS notifications for this center
                </CardTitle>
              </CardHeader>
              <CardContent>
                {smsLogs.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No SMS sent for this center yet.</p>
                ) : (
                  <div className="space-y-2">
                    {smsLogs.map((s: any) => (
                      <div key={s.id} className="rounded-lg border p-3 text-sm">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs">{s.to_number}</span>
                          <Badge variant={s.status === "sent" ? "default" : s.status === "failed" ? "destructive" : "outline"}>
                            {s.status}
                          </Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{s.message}</p>
                        <p className="mt-1 text-[10px] text-muted-foreground">{s.sent_at}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="ai">
            <AiDiagnosePanel centerId={id!} />
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}

function Row({ k, v }: { k: string; v: any }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-dashed py-1">
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="font-mono text-xs">{v ?? "—"}</dd>
    </div>
  );
}
