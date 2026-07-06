import { Alert } from "@/lib/types";
import { AlertTriangle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";

export function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  return (
    <div className="bg-card rounded-xl border p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-card-foreground mb-4 flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-warning" />
        Active Alerts ({alerts.length})
      </h3>
      <div className="space-y-3">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={cn(
              "flex items-start gap-3 p-3 rounded-lg border",
              alert.severity === "critical" ? "bg-destructive/5 border-destructive/20" : "bg-warning/5 border-warning/20"
            )}
          >
            <AlertCircle className={cn("w-4 h-4 mt-0.5 shrink-0", alert.severity === "critical" ? "text-destructive" : "text-warning")} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Link to={`/health-centers/${alert.center_id}`} className="text-sm font-semibold text-card-foreground hover:text-primary transition-colors">
                  {alert.center_name}
                </Link>
                <span className={cn(
                  "text-[10px] font-bold uppercase px-1.5 py-0.5 rounded",
                  alert.severity === "critical" ? "bg-destructive/15 text-destructive" : "bg-warning/15 text-warning"
                )}>
                  {alert.severity}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{alert.message}</p>
              <p className="text-[10px] text-muted-foreground/60 mt-1">{new Date(alert.timestamp).toLocaleString()}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
