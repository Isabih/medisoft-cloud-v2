import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader, StatusBadge } from "@/components/DashboardWidgets";
import { AlertsPanel } from "@/components/AlertsPanel";
import { SyncCharts } from "@/components/SyncCharts";
import { UnregisteredDbsWidget } from "@/components/UnregisteredDbsWidget";
import { CloudServerWidget } from "@/components/CloudServerWidget";
import { DatabaseIntegrityPanel } from "@/components/DatabaseIntegrityPanel";
import { LiveStreamChart } from "@/components/LiveStreamChart";
import { AutoHealButton } from "@/components/AutoHealButton";
import {
  fetchCentersLive,
  fetchDashboardKPIs,
  fetchActiveAlerts,
  fetchCloudStatus,
} from "@/lib/api";
import { CenterLive, DashboardKPIs, Alert, CloudStatus } from "@/lib/types";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";
import {
  Building2,
  Wifi,
  WifiOff,
  AlertTriangle,
  Loader2,
  ShieldCheck,
  Activity,
  HardDrive,
  Search,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  ChevronUp,
  ChevronDown,
  Bell,
  BarChart3,
  LineChart,
  ShieldAlert,
  Database,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

type SortKey =
  | "name"
  | "status"
  | "last_seen"
  | "seconds_behind"
  | "cpu_usage"
  | "ram_usage"
  | "disk_usage"
  | "backup_status"
  | "unresolved_alerts";

type SortDir = "asc" | "desc";

const safeText = (value?: string | null, fallback = "—") => {
  if (value == null || value === "") return fallback;
  return value;
};

const safeLower = (value?: string | null) => (value || "").toLowerCase();

const safeNumber = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const KPICard = ({
  title,
  value,
  icon,
  variant = "default",
  hint,
}: {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  hint?: string;
  variant?: "default" | "success" | "warning" | "danger";
}) => {
  const variantStyles = {
    default: "bg-card border",
    success: "bg-success/5 border border-success/20",
    warning: "bg-warning/5 border border-warning/20",
    danger: "bg-destructive/5 border border-destructive/20",
  };

  const iconBg = {
    default: "bg-primary/10 text-primary",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    danger: "bg-destructive/15 text-destructive",
  };

  return (
    <div
      className={cn(
        "rounded-2xl p-4 shadow-sm transition hover:shadow-md",
        variantStyles[variant]
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
          <p className="mt-1 text-2xl font-bold text-card-foreground">{value}</p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>

        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl",
            iconBg[variant]
          )}
        >
          {icon}
        </div>
      </div>
    </div>
  );
};

const ResourceCell = ({ value }: { value: number | null | undefined }) => {
  const safe = safeNumber(value, 0);
  const color =
    safe > 90 ? "text-destructive" : safe > 80 ? "text-warning" : "text-success";

  return (
    <div className="flex min-w-[90px] items-center gap-2">
      <Progress value={safe} className="h-1.5 flex-1" />
      <span className={cn("text-xs font-mono font-bold", color)}>{safe}%</span>
    </div>
  );
};

const HeartbeatCell = ({ lastSeen }: { lastSeen?: string | null }) => {
  if (!lastSeen) return <span className="text-xs text-muted-foreground">—</span>;

  const now = new Date();
  const seen = new Date(lastSeen);

  if (Number.isNaN(seen.getTime())) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const diffSec = Math.floor((now.getTime() - seen.getTime()) / 1000);
  const isStale = diffSec > 120;
  const label =
    diffSec < 60
      ? `${diffSec}s ago`
      : diffSec < 3600
      ? `${Math.floor(diffSec / 60)}m ago`
      : `${Math.floor(diffSec / 3600)}h ago`;

  return (
    <span
      className={cn(
        "text-xs font-mono",
        isStale ? "font-bold text-destructive" : "text-muted-foreground"
      )}
    >
      {label}
    </span>
  );
};

const ReplicaBadge = ({
  io,
  sql,
}: {
  io?: string | null;
  sql?: string | null;
}) => {
  const ioOk = io === "Yes";
  const sqlOk = sql === "Yes";

  if (ioOk && sqlOk) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-success">
        <CheckCircle className="h-3 w-3" />
        OK
      </span>
    );
  }

  if (ioOk || sqlOk) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-warning">
        <AlertTriangle className="h-3 w-3" />
        Partial
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-destructive">
      <XCircle className="h-3 w-3" />
      Stopped
    </span>
  );
};

const LagCell = ({ seconds }: { seconds: number | null | undefined }) => {
  if (seconds == null) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const safe = safeNumber(seconds, 0);
  const color =
    safe > 300 ? "font-bold text-destructive" : safe > 60 ? "text-warning" : "text-success";

  return <span className={cn("text-xs font-mono", color)}>{safe}s</span>;
};

const EmptyMetricCard = ({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
}) => {
  return (
    <div className="rounded-2xl border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        {icon}
        <h3 className="text-sm font-semibold text-card-foreground">{title}</h3>
      </div>
      <div className="flex min-h-[180px] flex-col items-center justify-center rounded-xl border border-dashed bg-muted/10 p-6 text-center">
        <p className="text-sm font-medium text-card-foreground">No data yet</p>
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
};

const DashboardPage = () => {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const {
    data: centers = [],
    isPending: loadingCenters,
    isFetching: fetchingCenters,
  } = useQuery<CenterLive[]>({
    queryKey: ["centers-live"],
    queryFn: async () => (await fetchCentersLive()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 5000,
  });

  const {
    data: kpis,
    isFetching: fetchingKpis,
  } = useQuery<DashboardKPIs>({
    queryKey: ["dashboard-kpis"],
    queryFn: async () => (await fetchDashboardKPIs()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 5000,
  });

  const {
    data: alerts = [],
    isFetching: fetchingAlerts,
  } = useQuery<Alert[]>({
    queryKey: ["alerts-active"],
    queryFn: async () => (await fetchActiveAlerts()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 5000,
  });

  const {
    data: cloudStatus,
  } = useQuery<CloudStatus>({
    queryKey: ["cloud-status"],
    queryFn: async () => (await fetchCloudStatus()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 5000,
  });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return sortDir === "asc" ? (
      <ChevronUp className="h-3 w-3" />
    ) : (
      <ChevronDown className="h-3 w-3" />
    );
  };

  const filtered = useMemo(() => {
    const q = search.toLowerCase();

    return [...centers]
      .filter((c) => {
        if (!search) return true;

        return (
          safeLower(c.name).includes(q) ||
          safeLower(c.database_name).includes(q) ||
          safeLower(c.province).includes(q) ||
          safeLower(c.district).includes(q) ||
          safeLower(c.foss_id).includes(q)
        );
      })
      .sort((a, b) => {
        let cmp = 0;

        switch (sortKey) {
          case "name":
            cmp = safeText(a.name, "").localeCompare(safeText(b.name, ""));
            break;
          case "status":
            cmp = safeText(a.status, "").localeCompare(safeText(b.status, ""));
            break;
          case "last_seen":
            cmp =
              new Date(a.last_seen || 0).getTime() -
              new Date(b.last_seen || 0).getTime();
            break;
          case "seconds_behind":
            cmp =
              safeNumber(a.seconds_behind, 9999) - safeNumber(b.seconds_behind, 9999);
            break;
          case "cpu_usage":
            cmp = safeNumber(a.cpu_usage) - safeNumber(b.cpu_usage);
            break;
          case "ram_usage":
            cmp = safeNumber(a.ram_usage) - safeNumber(b.ram_usage);
            break;
          case "disk_usage":
            cmp = safeNumber(a.disk_usage) - safeNumber(b.disk_usage);
            break;
          case "unresolved_alerts":
            cmp = safeNumber(a.unresolved_alerts) - safeNumber(b.unresolved_alerts);
            break;
          default:
            cmp = 0;
        }

        return sortDir === "desc" ? -cmp : cmp;
      });
  }, [centers, search, sortKey, sortDir]);

  if (loadingCenters && centers.length === 0) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  const k = kpis ?? {
    total_centers: centers.length,
    online: centers.filter((c) => c.status === "online").length,
    partial: centers.filter((c) => c.status === "partial").length,
    offline: centers.filter((c) => c.status === "offline").length,
    critical_alerts: alerts.filter((a) => a.severity === "critical").length,
    warning_alerts: alerts.filter((a) => a.severity === "warning").length,
    missing_backups: centers.filter((c) => c.backup_status !== "success").length,
    high_lag_centers: centers.filter((c) => safeNumber(c.seconds_behind) > 60).length,
    high_ram_centers: centers.filter((c) => safeNumber(c.ram_usage) > 85).length,
    high_disk_centers: centers.filter((c) => safeNumber(c.disk_usage) > 85).length,
  };

  const hasLiveData = filtered.length > 0;
  const isUpdating = fetchingCenters || fetchingKpis || fetchingAlerts;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          title="Dashboard"
          subtitle="Real-time monitoring across all health centers"
        />

        <div className="flex items-center justify-between">
          <div className="text-xs text-muted-foreground">
            Live infrastructure and health center status
          </div>

          {isUpdating && (
            <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground shadow-sm">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Updating…
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <KPICard
            title="Total Health Centers"
            value={k.total_centers}
            icon={<Building2 className="h-4 w-4" />}
            hint="Registered facilities being monitored"
          />
          <KPICard
            title="Online"
            value={k.online}
            icon={<Wifi className="h-4 w-4" />}
            variant="success"
            hint="Healthy and actively reporting"
          />
          <KPICard
            title="Partial"
            value={k.partial}
            icon={<AlertTriangle className="h-4 w-4" />}
            variant="warning"
            hint="Need attention but still responding"
          />
          <KPICard
            title="Offline"
            value={k.offline}
            icon={<WifiOff className="h-4 w-4" />}
            variant="danger"
            hint="Not currently reachable"
          />
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          <KPICard
            title="Critical Alerts"
            value={k.critical_alerts}
            icon={<AlertCircle className="h-4 w-4" />}
            variant="danger"
          />
          <KPICard
            title="Warning Alerts"
            value={k.warning_alerts}
            icon={<Bell className="h-4 w-4" />}
            variant="warning"
          />
          <KPICard
            title="Missing Backups"
            value={k.missing_backups}
            icon={<ShieldCheck className="h-4 w-4" />}
            variant={k.missing_backups > 0 ? "danger" : "success"}
          />
          <KPICard
            title="High Lag"
            value={k.high_lag_centers}
            icon={<Clock className="h-4 w-4" />}
            variant={k.high_lag_centers > 0 ? "warning" : "success"}
          />
          <KPICard
            title="High Disk Usage"
            value={k.high_disk_centers}
            icon={<HardDrive className="h-4 w-4" />}
            variant={k.high_disk_centers > 0 ? "warning" : "success"}
          />
          <KPICard
            title="High DB Drift"
            value={k.high_drift_databases ?? 0}
            icon={<Database className="h-4 w-4" />}
            variant={(k.high_drift_databases ?? 0) > 0 ? "warning" : "success"}
          />
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="xl:col-span-2">{cloudStatus && <CloudServerWidget data={cloudStatus} />}</div>
          <DatabaseIntegrityPanel />
        </div>

        <LiveStreamChart />

        <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
          <div className="flex flex-col gap-3 border-b p-4 md:flex-row md:items-center md:justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-card-foreground">
              <Activity className="h-4 w-4 text-primary" />
              Currently Reporting Health Centers ({filtered.length})
            </h3>

            {hasLiveData && (
              <div className="relative w-full md:max-w-sm">
                <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search by center, database, FOSA ID, province, district..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-9 pl-9 text-sm"
                />
              </div>
            )}
          </div>

          {!hasLiveData ? (
            <div className="p-8 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                <Activity className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-semibold text-card-foreground">
                No live health center activity yet
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Registered centers will appear here after heartbeat and monitoring data start
                syncing.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1100px] text-xs">
                <thead>
                  <tr className="border-b bg-muted/40">
                    {[
                      { key: "name" as SortKey, label: "Name" },
                      { key: null, label: "Province" },
                      { key: null, label: "District" },
                      { key: null, label: "Database" },
                      { key: "status" as SortKey, label: "Status" },
                      { key: "last_seen" as SortKey, label: "Heartbeat" },
                      { key: null, label: "Replication" },
                      { key: "seconds_behind" as SortKey, label: "Lag" },
                      { key: null, label: "Backup" },
                      { key: "cpu_usage" as SortKey, label: "CPU" },
                      { key: "ram_usage" as SortKey, label: "RAM" },
                      { key: "disk_usage" as SortKey, label: "Disk" },
                      { key: null, label: "Drift" },
                      { key: null, label: "DB Health" },
                      { key: "unresolved_alerts" as SortKey, label: "Alerts" },
                      { key: null, label: "Heal" },
                    ].map(({ key, label }) => (
                      <th
                        key={label}
                        className={cn(
                          "whitespace-nowrap p-3 text-left font-semibold text-muted-foreground",
                          key && "cursor-pointer select-none hover:text-foreground"
                        )}
                        onClick={key ? () => toggleSort(key) : undefined}
                      >
                        <span className="inline-flex items-center gap-1">
                          {label}
                          {key && <SortIcon col={key} />}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {filtered.map((c) => (
                    <tr
                      key={c.center_id}
                      className="border-b transition-colors last:border-0 hover:bg-muted/30"
                    >
                      <td className="p-3">
                        <Link
                          to={`/health-centers/${c.center_id}`}
                          className="font-semibold text-card-foreground transition-colors hover:text-primary"
                        >
                          {safeText(c.name)}
                        </Link>
                      </td>
                      <td className="p-3 text-muted-foreground">{safeText(c.province)}</td>
                      <td className="p-3 text-muted-foreground">{safeText(c.district)}</td>
                      <td className="p-3 font-mono text-muted-foreground">
                        {safeText(c.database_name)}
                      </td>
                      <td className="p-3">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="p-3">
                        <HeartbeatCell lastSeen={c.last_seen} />
                      </td>
                      <td className="p-3">
                        <ReplicaBadge io={c.replica_io} sql={c.replica_sql} />
                      </td>
                      <td className="p-3">
                        <LagCell seconds={c.seconds_behind} />
                      </td>
                      <td className="p-3">
                        {c.backup_status === "success" ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-success">
                            <CheckCircle className="h-3 w-3" />
                            OK
                          </span>
                        ) : c.backup_status === "failed" ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-destructive">
                            <XCircle className="h-3 w-3" />
                            Failed
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="p-3">
                        <ResourceCell value={c.cpu_usage} />
                      </td>
                      <td className="p-3">
                        <ResourceCell value={c.ram_usage} />
                      </td>
                      <td className="p-3">
                        <ResourceCell value={c.disk_usage} />
                      </td>
                      <td className="p-3">
                        {c.drift_detected ? (
                          <Badge
                            variant="secondary"
                            className="border border-warning/30 bg-warning/15 text-[10px] text-warning"
                          >
                            Drift
                          </Badge>
                        ) : (
                          <span className="text-[11px] text-success">✓</span>
                        )}
                      </td>
                      <td className="p-3">
                        <div className="min-w-[120px]">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-semibold">{c.data_health_score ?? "—"}%</span>
                            <span className="text-[10px] text-muted-foreground">{c.rows_difference ?? 0} rows</span>
                          </div>
                          <Progress value={Number(c.data_health_score ?? 0)} className="mt-1 h-1.5" />
                        </div>
                      </td>
                      <td className="p-3">
                        {safeNumber(c.unresolved_alerts) > 0 ? (
                          <Badge variant="destructive" className="text-[10px]">
                            {safeNumber(c.unresolved_alerts)}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </td>
                      <td className="p-3">
                        <AutoHealButton
                          channelName={(c as any).replication_channel || c.database_name}
                          centerId={c.center_id}
                          centerName={c.name}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {hasLiveData ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <SyncCharts />
            </div>

            <div className="space-y-6">
              <UnregisteredDbsWidget />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
            <div className="xl:col-span-1">
              <EmptyMetricCard
                title="Sync Activity (24h)"
                description="Charts will appear after live sync metrics are collected."
                icon={<LineChart className="h-4 w-4 text-primary" />}
              />
            </div>
            <div className="xl:col-span-1">
              <EmptyMetricCard
                title="Data Volume/Hour (MB)"
                description="Hourly data usage will be shown once monitored traffic is available."
                icon={<BarChart3 className="h-4 w-4 text-primary" />}
              />
            </div>
            <div className="xl:col-span-1">
              <EmptyMetricCard
                title="Risk Score by Center"
                description="Risk scoring appears after enough monitoring indicators are collected."
                icon={<ShieldAlert className="h-4 w-4 text-primary" />}
              />
            </div>
            <div className="xl:col-span-1">
              <UnregisteredDbsWidget />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <AlertsPanel alerts={alerts} />
          <div className="rounded-2xl border bg-card p-5 shadow-sm">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-card-foreground">
              <Building2 className="h-4 w-4 text-primary" />
              Monitoring Notes
            </h3>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>• Online centers are actively sending heartbeats and operational metrics.</p>
              <p>• Partial status usually means replication, backup, or connectivity needs review.</p>
              <p>• Drift alerts indicate schema mismatch against the expected baseline.</p>
              <p>• High RAM, disk, or lag should be reviewed before they become outages.</p>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default DashboardPage;