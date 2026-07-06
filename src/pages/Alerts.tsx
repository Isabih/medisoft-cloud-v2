import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { fetchActiveAlerts, resolveAlert } from "@/lib/api";
import { Alert } from "@/lib/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertCircle, AlertTriangle, CheckCircle, Search, Loader2, Bell, Clock, Shield, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";
import { toast } from "sonner";

const ALERT_TYPE_LABELS: Record<string, string> = {
  heartbeat_missing: "Heartbeat Missing",
  replication_stopped: "Replication Stopped",
  high_lag: "High Lag",
  backup_missing: "Backup Missing",
  high_disk: "High Disk",
  high_ram: "High RAM",
  high_cpu: "High CPU",
  drift_detected: "Drift Detected",
  no_sync: "No Sync",
  partial_sync: "Partial Sync",
  data_drop: "Data Drop",
};

const AlertRow = ({ alert, onResolve, resolving }: { alert: Alert; onResolve: (id: string) => void; resolving: boolean }) => {
  const isCritical = alert.severity === "critical";

  return (
    <div className={cn(
      "flex items-start gap-4 p-4 rounded-lg border transition-all",
      isCritical ? "bg-destructive/5 border-destructive/20" : "bg-warning/5 border-warning/20",
      alert.resolved_at && "opacity-60 bg-muted/30 border-border"
    )}>
      <div className="mt-0.5">
        {isCritical ? (
          <AlertCircle className="w-5 h-5 text-destructive" />
        ) : (
          <AlertTriangle className="w-5 h-5 text-warning" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Link to={`/health-centers/${alert.center_id}`} className="text-sm font-bold text-card-foreground hover:text-primary transition-colors">
            {alert.center_name}
          </Link>
          <Badge variant={isCritical ? "destructive" : "secondary"} className={cn(
            "text-[10px] uppercase",
            !isCritical && "bg-warning/15 text-warning border border-warning/30"
          )}>
            {alert.severity}
          </Badge>
          <Badge variant="outline" className="text-[10px]">
            {ALERT_TYPE_LABELS[alert.type] ?? alert.type}
          </Badge>
          {alert.resolved_at && (
            <Badge variant="outline" className="text-[10px] text-success border-success/30 bg-success/10">
              <CheckCircle className="w-2.5 h-2.5 mr-1" /> Resolved
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground mt-1">{alert.message}</p>
        <div className="flex items-center gap-4 mt-2 text-[11px] text-muted-foreground/70">
          <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(alert.timestamp).toLocaleString()}</span>
          {alert.resolved_at && (
            <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" />Resolved: {new Date(alert.resolved_at).toLocaleString()}</span>
          )}
        </div>
      </div>
      {!alert.resolved_at && (
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 text-xs"
          onClick={() => onResolve(alert.id)}
          disabled={resolving}
        >
          {resolving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3 mr-1" />}
          Resolve
        </Button>
      )}
    </div>
  );
};

const AlertsPage = () => {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const queryClient = useQueryClient();

  const { data: alerts = [], isLoading } = useQuery<Alert[]>({
    queryKey: ["alerts-active"],
    queryFn: async () => (await fetchActiveAlerts()).data,
    refetchInterval: 15000,
  });

  const resolveMutation = useMutation({
    mutationFn: resolveAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts-active"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
      queryClient.invalidateQueries({ queryKey: ["centers-live"] });
      toast.success("Alert resolved");
    },
    onError: () => toast.error("Failed to resolve alert"),
  });

  const criticalAlerts = alerts.filter(a => a.severity === "critical" && !a.resolved_at);
  const warningAlerts = alerts.filter(a => a.severity === "warning" && !a.resolved_at);
  const resolvedAlerts = alerts.filter(a => !!a.resolved_at);

  const filterAlerts = (list: Alert[]) => {
    return list
      .filter(a => !search || a.center_name.toLowerCase().includes(search.toLowerCase()) || a.message.toLowerCase().includes(search.toLowerCase()))
      .filter(a => typeFilter === "all" || a.type === typeFilter);
  };

  const alertTypes = [...new Set(alerts.map(a => a.type))];

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <PageHeader title="Alerts" subtitle="Monitor and manage system alerts across all health centers">
        <div className="flex items-center gap-3">
          <Badge variant="destructive" className="text-xs">{criticalAlerts.length} Critical</Badge>
          <Badge variant="secondary" className="bg-warning/15 text-warning border border-warning/30 text-xs">{warningAlerts.length} Warning</Badge>
        </div>
      </PageHeader>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search alerts..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9 h-9 text-sm"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-[200px] h-9 text-sm">
            <SelectValue placeholder="Filter by type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            {alertTypes.map(t => (
              <SelectItem key={t} value={t}>{ALERT_TYPE_LABELS[t] ?? t}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(search || typeFilter !== "all") && (
          <Button variant="ghost" size="sm" onClick={() => { setSearch(""); setTypeFilter("all"); }}>
            <X className="w-3 h-3 mr-1" /> Clear
          </Button>
        )}
      </div>

      <Tabs defaultValue="critical" className="space-y-4">
        <TabsList>
          <TabsTrigger value="critical" className="gap-1.5">
            <AlertCircle className="w-3.5 h-3.5" /> Critical ({filterAlerts(criticalAlerts).length})
          </TabsTrigger>
          <TabsTrigger value="warning" className="gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Warning ({filterAlerts(warningAlerts).length})
          </TabsTrigger>
          <TabsTrigger value="resolved" className="gap-1.5">
            <CheckCircle className="w-3.5 h-3.5" /> Resolved ({filterAlerts(resolvedAlerts).length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="critical" className="space-y-3">
          {filterAlerts(criticalAlerts).length === 0 ? (
            <div className="bg-card rounded-xl border p-12 text-center">
              <Shield className="w-10 h-10 text-success mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">No critical alerts — system is healthy!</p>
            </div>
          ) : (
            filterAlerts(criticalAlerts).map(a => (
              <AlertRow key={a.id} alert={a} onResolve={id => resolveMutation.mutate(id)} resolving={resolveMutation.isPending} />
            ))
          )}
        </TabsContent>

        <TabsContent value="warning" className="space-y-3">
          {filterAlerts(warningAlerts).length === 0 ? (
            <div className="bg-card rounded-xl border p-12 text-center">
              <Shield className="w-10 h-10 text-success mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">No warning alerts.</p>
            </div>
          ) : (
            filterAlerts(warningAlerts).map(a => (
              <AlertRow key={a.id} alert={a} onResolve={id => resolveMutation.mutate(id)} resolving={resolveMutation.isPending} />
            ))
          )}
        </TabsContent>

        <TabsContent value="resolved" className="space-y-3">
          {filterAlerts(resolvedAlerts).length === 0 ? (
            <div className="bg-card rounded-xl border p-12 text-center">
              <Bell className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">No resolved alerts yet.</p>
            </div>
          ) : (
            filterAlerts(resolvedAlerts).map(a => (
              <AlertRow key={a.id} alert={a} onResolve={id => resolveMutation.mutate(id)} resolving={resolveMutation.isPending} />
            ))
          )}
        </TabsContent>
      </Tabs>
    </DashboardLayout>
  );
};

export default AlertsPage;
