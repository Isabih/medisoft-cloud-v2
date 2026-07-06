import { useQuery } from "@tanstack/react-query";
import { fetchMonitoredDatabases } from "@/lib/api";
import { MonitoredDatabase } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Loader2, Grid3X3 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Link } from "react-router-dom";

export function ReplicaHeatmap() {
  const { data: databases = [], isLoading } = useQuery<MonitoredDatabase[]>({
    queryKey: ["monitored-databases"],
    queryFn: async () => (await fetchMonitoredDatabases()).data,
    refetchInterval: 30000,
  });

  const getCellColor = (db: MonitoredDatabase) => {
    if (db.replica_status === "offline") return "bg-destructive hover:bg-destructive/80";
    if (db.replica_status === "partial" || db.drift_detected) return "bg-warning hover:bg-warning/80";
    return "bg-success hover:bg-success/80";
  };

  return (
    <div className="bg-card rounded-xl border p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-card-foreground mb-4 flex items-center gap-2">
        <Grid3X3 className="w-4 h-4 text-primary" />
        Replica Status Overview
      </h3>

      {isLoading ? (
        <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : databases.length === 0 ? (
        <p className="text-xs text-muted-foreground">No databases being monitored.</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5">
            {databases.map((db) => (
              <Tooltip key={db.id}>
                <TooltipTrigger asChild>
                  <Link
                    to={`/health-centers/${db.health_center_id}`}
                    className={cn(
                      "w-8 h-8 rounded-md transition-colors cursor-pointer flex items-center justify-center",
                      getCellColor(db)
                    )}
                  >
                    <span className="text-[8px] font-bold text-white/90 leading-none text-center truncate px-0.5">
                      {db.health_center_name.slice(0, 3).toUpperCase()}
                    </span>
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  <p className="font-semibold">{db.health_center_name}</p>
                  <p className="text-muted-foreground">{db.database_name}</p>
                  <p>Status: <span className="font-medium capitalize">{db.replica_status}</span></p>
                  {db.drift_detected && <p className="text-warning">⚠ Schema drift detected</p>}
                  <p>{db.rows_count.toLocaleString()} rows • {db.data_size_mb.toFixed(1)} MB</p>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 mt-3 pt-3 border-t">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="w-3 h-3 rounded-sm bg-success" /> OK
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="w-3 h-3 rounded-sm bg-warning" /> Partial/Drift
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="w-3 h-3 rounded-sm bg-destructive" /> Offline
            </div>
          </div>
        </>
      )}
    </div>
  );
}
