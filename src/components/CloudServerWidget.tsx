import {
  Server,
  Cpu,
  MemoryStick,
  HardDrive,
  Clock3,
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CloudStatus } from "@/lib/types";

const StatCard = ({
  title,
  value,
  sub,
  icon,
}: {
  title: string;
  value: string | number;
  sub?: string;
  icon: React.ReactNode;
}) => (
  <div className="rounded-2xl border bg-card p-4 shadow-sm">
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </p>
        <p className="mt-1 text-xl font-bold text-card-foreground">{value}</p>
        {sub ? <p className="mt-1 text-xs text-muted-foreground">{sub}</p> : null}
      </div>
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
        {icon}
      </div>
    </div>
  </div>
);

const ResourceMeter = ({
  label,
  percent,
  used,
  total,
  free,
  icon,
}: {
  label: string;
  percent: number;
  used: string;
  total: string;
  free: string;
  icon: React.ReactNode;
}) => {
  const tone =
    percent > 90
      ? "text-destructive"
      : percent > 80
      ? "text-warning"
      : "text-success";

  return (
    <div className="rounded-2xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            {icon}
          </div>
          <div>
            <p className="text-sm font-semibold text-card-foreground">{label}</p>
            <p className="text-xs text-muted-foreground">
              Used {used} / {total}
            </p>
          </div>
        </div>
        <span className={cn("text-sm font-bold", tone)}>{percent}%</span>
      </div>

      <Progress value={percent} className="h-2" />

      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>Free: {free}</span>
        <span>Total: {total}</span>
      </div>
    </div>
  );
};

const StatusPill = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => {
  const v = value.toLowerCase();
  const isGood = v === "online" || v === "healthy" || v === "connected";
  const isWarn = v === "warning" || v === "degraded" || v === "partial";

  return (
    <div className="flex items-center justify-between rounded-xl border bg-muted/20 px-3 py-2">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span
        className={cn(
          "inline-flex items-center gap-1 text-xs font-semibold",
          isGood
            ? "text-success"
            : isWarn
            ? "text-warning"
            : "text-destructive"
        )}
      >
        {isGood ? (
          <CheckCircle2 className="h-3.5 w-3.5" />
        ) : isWarn ? (
          <AlertTriangle className="h-3.5 w-3.5" />
        ) : (
          <XCircle className="h-3.5 w-3.5" />
        )}
        {value}
      </span>
    </div>
  );
};

const formatLastSeen = (date?: string) => {
  if (!date) return "—";
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return "—";

  const diff = Math.floor((Date.now() - parsed.getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

export const CloudServerWidget = ({ data }: { data: CloudStatus }) => {
  const serverTone =
    data.server_status === "online"
      ? "success"
      : data.server_status === "warning"
      ? "warning"
      : "destructive";

  return (
    <div className="rounded-3xl border bg-card p-5 shadow-sm">
      <div className="mb-5 flex flex-col gap-3 border-b pb-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-card-foreground">
            <Server className="h-5 w-5 text-primary" />
            Cloud Infrastructure Status
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Live health of the central monitoring server
          </p>
        </div>

        <Badge
          variant="secondary"
          className={cn(
            "w-fit border px-3 py-1 text-xs",
            serverTone === "success" &&
              "border-success/30 bg-success/10 text-success",
            serverTone === "warning" &&
              "border-warning/30 bg-warning/10 text-warning",
            serverTone === "destructive" &&
              "border-destructive/30 bg-destructive/10 text-destructive"
          )}
        >
          {data.server_name} • {data.server_status}
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
        <StatCard
          title="Server Uptime"
          value={data.uptime}
          sub={`Updated ${formatLastSeen(data.last_updated)}`}
          icon={<Clock3 className="h-4 w-4" />}
        />
        <StatCard
          title="CPU Cores"
          value={data.cpu_cores}
          sub={`Load avg: ${data.load_average}`}
          icon={<Cpu className="h-4 w-4" />}
        />
        <StatCard
          title="Free RAM"
          value={`${data.ram_free_gb} GB`}
          sub={`Total ${data.ram_total_gb} GB`}
          icon={<MemoryStick className="h-4 w-4" />}
        />
        <StatCard
          title="Free Disk"
          value={`${data.disk_free_gb} GB`}
          sub={`Total ${data.disk_total_gb} GB`}
          icon={<HardDrive className="h-4 w-4" />}
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ResourceMeter
          label="CPU Usage"
          percent={data.cpu_usage}
          used={`${data.cpu_usage}%`}
          total={`${data.cpu_cores} cores`}
          free={`${Math.max(0, 100 - data.cpu_usage)}% idle`}
          icon={<Cpu className="h-4 w-4" />}
        />
        <ResourceMeter
          label="RAM Usage"
          percent={Math.round((data.ram_used_gb / data.ram_total_gb) * 100)}
          used={`${data.ram_used_gb} GB`}
          total={`${data.ram_total_gb} GB`}
          free={`${data.ram_free_gb} GB`}
          icon={<MemoryStick className="h-4 w-4" />}
        />
        <ResourceMeter
          label="Disk Usage"
          percent={data.disk_percent}
          used={`${data.disk_used_gb} GB`}
          total={`${data.disk_total_gb} GB`}
          free={`${data.disk_free_gb} GB`}
          icon={<HardDrive className="h-4 w-4" />}
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
        <StatusPill label="API" value={data.api_status} />
        <StatusPill label="Database" value={data.database_status} />
        <StatusPill label="Internet" value={data.internet_status} />
      </div>

      <div className="mt-5 rounded-2xl border bg-muted/10 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-card-foreground">
          <Activity className="h-4 w-4 text-primary" />
          Real-Time Server Notes
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 text-sm text-muted-foreground md:grid-cols-2">
          <p>• Central server resources are monitored separately from health centers.</p>
          <p>• CPU, memory, and disk trends help catch overload before outage happens.</p>
          <p>• API and database badges show whether monitoring services are healthy.</p>
          <p>• This panel can later be extended with bandwidth, temperature, and process checks.</p>
        </div>
      </div>
    </div>
  );
};