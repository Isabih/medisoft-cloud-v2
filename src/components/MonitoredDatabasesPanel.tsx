import { useQuery } from "@tanstack/react-query";
import { fetchMonitoredDatabases } from "@/lib/api";
import { MonitoredDatabase } from "@/lib/types";
import { Database, AlertTriangle, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";

const ReplicaStatusDot = ({ status }: { status: "ok" | "offline" | "partial" }) => {
  const colors = {
    ok: "bg-success",
    offline: "bg-destructive",
    partial: "bg-warning",
  };
  return <span className={cn("w-2.5 h-2.5 rounded-full inline-block", colors[status])} />;
};

export function MonitoredDatabasesPanel() {
  const { data: databases = [], isLoading } = useQuery<MonitoredDatabase[]>({
    queryKey: ["monitored-databases"],
    queryFn: async () => (await fetchMonitoredDatabases()).data,
    refetchInterval: 30000,
  });

  const okCount = databases.filter(d => d.replica_status === "ok").length;
  const offlineCount = databases.filter(d => d.replica_status === "offline").length;
  const driftCount = databases.filter(d => d.drift_detected).length;

  return (
    <div className="bg-card rounded-xl border p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-card-foreground mb-4 flex items-center gap-2">
        <Database className="w-4 h-4 text-primary" />
        Monitored Databases ({databases.length})
      </h3>

      {/* Summary badges */}
      <div className="flex gap-2 mb-4">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-success/15 text-success border border-success/30">
          <CheckCircle className="w-3 h-3" /> {okCount} OK
        </span>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-destructive/15 text-destructive border border-destructive/30">
          <XCircle className="w-3 h-3" /> {offlineCount} Offline
        </span>
        {driftCount > 0 && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-warning/15 text-warning border border-warning/30">
            <AlertTriangle className="w-3 h-3" /> {driftCount} Drift
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : databases.length === 0 ? (
        <p className="text-xs text-muted-foreground">No monitored databases found.</p>
      ) : (
        <div className="space-y-2 max-h-[300px] overflow-y-auto">
          {databases.map((db) => (
            <Link
              key={db.id}
              to={`/health-centers/${db.health_center_id}`}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/30 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <ReplicaStatusDot status={db.replica_status} />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-card-foreground truncate">{db.health_center_name}</p>
                  <p className="text-xs font-mono text-muted-foreground truncate">{db.database_name}</p>
                </div>
              </div>
              <div className="text-right shrink-0 ml-2">
                <p className="text-xs text-muted-foreground">{db.rows_count.toLocaleString()} rows</p>
                <p className="text-xs text-muted-foreground">{db.data_size_mb.toFixed(1)} MB</p>
                {db.drift_detected && (
                  <span className="text-[10px] text-warning font-semibold">DRIFT</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
