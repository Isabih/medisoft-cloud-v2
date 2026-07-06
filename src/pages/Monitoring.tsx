import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader, StatusBadge } from "@/components/DashboardWidgets";
import {
  fetchHealthCenters,
  fetchHealthCenter,
  fetchDriftReport,
  fetchReplicationHistory,
  fetchMetricsHistory,
  fetchCenterTimeline,
} from "@/lib/api";
import { HealthCenter, DriftReport, TimelineEvent } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Database,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  HardDrive,
  Layers,
  Wifi,
  WifiOff,
  Loader2,
  Cpu,
  MemoryStick,
  HardDriveDownload,
  Search,
  Shield,
  Server,
  History,
  BarChart3,
  Radio,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";
import {
  matchesHealthCenterQuery,
  readRememberedHealthCenter,
  rememberSelectedHealthCenter,
  clearRememberedHealthCenter,
} from "@/lib/health-center-utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  AreaChart,
  Area,
  LineChart,
  Line,
} from "recharts";
import { Input } from "@/components/ui/input";

const safeText = (value?: string | null, fallback = "—") => {
  if (value == null || value === "") return fallback;
  return value;
};

const safeLower = (value?: string | null) => (value || "").toLowerCase();

const safeNumber = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const formatInteger = (value: unknown, fallback = "0") => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString() : fallback;
};

const formatMb = (value: unknown, fallback = "—") => {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(1)} MB` : fallback;
};

const formatDateTime = (value?: string | null, fallback = "—") => {
  if (!value) return fallback;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? fallback : d.toLocaleString();
};

const formatTimeOnly = (value?: string | null, fallback = "—") => {
  if (!value) return fallback;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? fallback : d.toLocaleTimeString();
};

const formatLastSeen = (value?: string | null, fallback = "—") => {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return fallback;

  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  return `${Math.floor(diffMin / 60)} hr ago`;
};

const ReplicaStatusIcon = ({
  center,
}: {
  center: HealthCenter;
}) => {
  const rep = center.replication;

  if (!rep) return <AlertTriangle className="h-5 w-5 text-warning" />;

  const isOk =
    rep.io_running === "Yes" &&
    rep.sql_running === "Yes" &&
    (rep.seconds_behind ?? 999) <= 5;

  const isPartial =
    rep.io_running === "Yes" || rep.sql_running === "Yes";

  if (isOk) return <CheckCircle className="h-5 w-5 text-success" />;
  if (isPartial) return <AlertTriangle className="h-5 w-5 text-warning" />;
  return <XCircle className="h-5 w-5 text-destructive" />;
};

const ResourceBlock = ({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value?: number | null;
  icon: any;
}) => {
  const safe = safeNumber(value, 0);

  return (
    <div className="flex items-center gap-3">
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1">
        <div className="mb-1 flex justify-between text-xs">
          <span className="text-muted-foreground">{label}</span>
          <span
            className={cn(
              "font-bold",
              safe > 80
                ? "text-destructive"
                : safe > 60
                ? "text-warning"
                : "text-success"
            )}
          >
            {safe}%
          </span>
        </div>
        <Progress value={safe} className="h-2" />
      </div>
    </div>
  );
};

const MonitoringPage = () => {
  const [selectedCenterId, setSelectedCenterId] = useState<string>(() => readRememberedHealthCenter());
  const [searchTerm, setSearchTerm] = useState("");

  const {
    data: centers = [],
    isPending: loadingCenters,
    isFetching: fetchingCenters,
  } = useQuery<HealthCenter[]>({
    queryKey: ["health-centers"],
    queryFn: async () => (await fetchHealthCenters()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 30000,
  });

  const selectedCenter = useMemo(
    () => centers.find((c) => c.id === selectedCenterId),
    [centers, selectedCenterId]
  );

  const {
    data: centerDetail,
    isFetching: fetchingCenterDetail,
  } = useQuery<HealthCenter>({
    queryKey: ["health-center", selectedCenterId],
    queryFn: async () => (await fetchHealthCenter(selectedCenterId)).data,
    enabled: !!selectedCenterId,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 15000,
  });

  const {
    data: driftReport,
    isFetching: fetchingDrift,
  } = useQuery<DriftReport>({
    queryKey: ["drift-report", selectedCenterId],
    queryFn: async () => (await fetchDriftReport(selectedCenterId)).data,
    enabled: !!selectedCenterId,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 30000,
  });

  const {
    data: replicationHistory = [],
    isFetching: fetchingReplicationHistory,
  } = useQuery<any[]>({
    queryKey: ["replication-history", selectedCenterId],
    queryFn: async () => (await fetchReplicationHistory(selectedCenterId)).data,
    enabled: !!selectedCenterId,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 30000,
  });

  const {
    data: metricsHistory = [],
    isFetching: fetchingMetricsHistory,
  } = useQuery<any[]>({
    queryKey: ["metrics-history", selectedCenterId],
    queryFn: async () => (await fetchMetricsHistory(selectedCenterId)).data,
    enabled: !!selectedCenterId,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 30000,
  });

  const {
    data: timeline = [],
    isFetching: fetchingTimeline,
  } = useQuery<TimelineEvent[]>({
    queryKey: ["center-timeline", selectedCenterId],
    queryFn: async () => (await fetchCenterTimeline(selectedCenterId)).data,
    enabled: !!selectedCenterId,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 30000,
  });

  const filteredCenters = useMemo(() => {
    return centers.filter((center) => matchesHealthCenterQuery(center, searchTerm));
  }, [centers, searchTerm]);

  useEffect(() => {
    if (!centers.length) return;

    const rememberedExists = centers.some((center) => center.id === selectedCenterId);
    if (selectedCenterId && rememberedExists) return;

    const fallbackId = filteredCenters[0]?.id || centers[0]?.id || "";
    if (fallbackId) {
      setSelectedCenterId(fallbackId);
      rememberSelectedHealthCenter(fallbackId);
    } else {
      clearRememberedHealthCenter();
    }
  }, [centers, filteredCenters, selectedCenterId]);

  const isUpdating =
    fetchingCenters ||
    fetchingCenterDetail ||
    fetchingDrift ||
    fetchingReplicationHistory ||
    fetchingMetricsHistory ||
    fetchingTimeline;

  const onlineCount = centers.filter((c) => c.status === "online").length;
  const offlineCount = centers.filter((c) => c.status === "offline").length;
  const partialCount = centers.filter((c) => c.status === "partial").length;
  const driftCount = centers.filter((c) => c.drift_detected).length;

  if (loadingCenters && centers.length === 0) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          title="Local Server Monitoring"
          subtitle="Real-time health center server monitoring using real source-side data"
        >
          <div className="flex items-center gap-2">
            {isUpdating && (
              <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs font-medium">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                <span className="text-muted-foreground">Updating...</span>
              </div>
            )}
          </div>
        </PageHeader>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Server className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Servers</p>
                <p className="text-xl font-bold text-card-foreground">{centers.length}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-success/10">
                <CheckCircle className="h-5 w-5 text-success" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Online</p>
                <p className="text-xl font-bold text-success">{onlineCount}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-warning/10">
                <AlertTriangle className="h-5 w-5 text-warning" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Partial</p>
                <p className="text-xl font-bold text-warning">{partialCount}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-destructive/10">
                <XCircle className="h-5 w-5 text-destructive" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Offline / Drift</p>
                <p className="text-xl font-bold text-destructive">
                  {offlineCount} / {driftCount}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <Card className="h-full">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Server className="h-4 w-4 text-primary" />
                  Select Local Server
                </CardTitle>

                <div className="relative mt-2">
                  <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search center, database, FOSA ID, province, district, AnyDesk..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="h-9 pl-9 text-sm"
                  />
                </div>
              </CardHeader>

              <CardContent className="pt-0">
                <div className="max-h-[560px] space-y-1.5 overflow-y-auto pr-1">
                  {filteredCenters.map((center) => (
                    <button
                      key={center.id}
                      onClick={() => {
                        setSelectedCenterId(center.id);
                        rememberSelectedHealthCenter(center.id);
                      }}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-all",
                        selectedCenterId === center.id
                          ? "border-primary bg-primary/5 shadow-sm"
                          : "border-transparent hover:bg-muted/50"
                      )}
                    >
                      <ReplicaStatusIcon center={center} />

                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-card-foreground">
                          {safeText(center.name)}
                        </p>
                        <p className="truncate text-xs font-mono text-muted-foreground">
                          {safeText(center.database_name)}
                        </p>
                        <p className="mt-0.5 text-[10px] text-muted-foreground">
                          FOSS ID: {safeText(center.foss_id)}
                        </p>
                      </div>

                      <div className="shrink-0 text-right">
                        <p className="text-[10px] text-muted-foreground">
                          {formatLastSeen(center.last_seen)}
                        </p>
                        <StatusBadge status={center.status} className="mt-1" />
                      </div>
                    </button>
                  ))}

                  {filteredCenters.length === 0 && (
                    <p className="py-4 text-center text-xs text-muted-foreground">
                      No health centers found.
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="lg:col-span-8">
            {!selectedCenterId || !centerDetail ? (
              <Card className="flex h-[400px] items-center justify-center">
                <div className="text-center">
                  <Server className="mx-auto mb-3 h-12 w-12 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">
                    Select a local server from the left to view live monitoring details
                  </p>
                </div>
              </Card>
            ) : (
              <Tabs defaultValue="overview" className="space-y-4">
                <TabsList>
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="replication">Replication</TabsTrigger>
                  <TabsTrigger value="drift">Drift Detection</TabsTrigger>
                  <TabsTrigger value="metrics">Metrics History</TabsTrigger>
                  <TabsTrigger value="timeline">Event Timeline</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-4">
                  <Card>
                    <CardContent className="p-5">
                      <div className="mb-4 flex items-center justify-between gap-4">
                        <div>
                          <h3 className="text-lg font-bold text-card-foreground">
                            {safeText(centerDetail.name)}
                          </h3>
                          <p className="text-sm font-mono text-muted-foreground">
                            {safeText(centerDetail.database_name)}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {safeText(centerDetail.province)} • {safeText(centerDetail.district)} • FOSS ID:{" "}
                            {safeText(centerDetail.foss_id)}
                          </p>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge status={centerDetail.status} />

                          {centerDetail.internet_status === "online" ? (
                            <Badge className="bg-success text-success-foreground">
                              <Wifi className="mr-1 h-3 w-3" />
                              Internet Online
                            </Badge>
                          ) : (
                            <Badge variant="destructive">
                              <WifiOff className="mr-1 h-3 w-3" />
                              Internet Offline
                            </Badge>
                          )}

                          {centerDetail.drift_detected && (
                            <Badge
                              variant="secondary"
                              className="border border-warning/30 bg-warning/15 text-warning"
                            >
                              <AlertTriangle className="mr-1 h-3 w-3" />
                              Drift
                            </Badge>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                        <div className="rounded-lg bg-muted/30 p-3">
                          <p className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Database className="h-3 w-3" />
                            Rows
                          </p>
                          <p className="text-lg font-bold text-card-foreground">
                            {formatInteger(centerDetail.rows_count ?? 0)}
                          </p>
                        </div>

                        <div className="rounded-lg bg-muted/30 p-3">
                          <p className="flex items-center gap-1 text-xs text-muted-foreground">
                            <HardDrive className="h-3 w-3" />
                            DB Size
                          </p>
                          <p className="text-lg font-bold text-card-foreground">
                            {formatMb(centerDetail.data_size_mb)}
                          </p>
                        </div>

                        <div className="rounded-lg bg-muted/30 p-3">
                          <p className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            Last Seen
                          </p>
                          <p className="text-sm font-semibold text-card-foreground">
                            {formatDateTime(centerDetail.last_seen)}
                          </p>
                        </div>

                        <div className="rounded-lg bg-muted/30 p-3">
                          <p className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Shield className="h-3 w-3" />
                            Backup
                          </p>
                          <p
                            className={cn(
                              "text-sm font-semibold",
                              centerDetail.last_backup?.status === "success"
                                ? "text-success"
                                : centerDetail.last_backup?.status === "failed"
                                ? "text-destructive"
                                : "text-muted-foreground"
                            )}
                          >
                            {centerDetail.last_backup?.status === "success"
                              ? "✓ Success"
                              : centerDetail.last_backup?.status === "failed"
                              ? "✗ Failed"
                              : "—"}
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm">Local Server Resources</CardTitle>
                    </CardHeader>

                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                        <ResourceBlock
                          label="CPU Usage"
                          value={centerDetail.cpu_usage}
                          icon={Cpu}
                        />
                        <ResourceBlock
                          label="RAM Usage"
                          value={centerDetail.ram_usage}
                          icon={MemoryStick}
                        />
                        <ResourceBlock
                          label="Disk Usage"
                          value={centerDetail.disk_usage}
                          icon={HardDriveDownload}
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3 border-t pt-3 md:grid-cols-4">
                        <div>
                          <p className="text-xs text-muted-foreground">Cloud Connection</p>
                          <p
                            className={cn(
                              "mt-1 text-sm font-semibold",
                              centerDetail.cloud_connection === "ok"
                                ? "text-success"
                                : "text-destructive"
                            )}
                          >
                            {centerDetail.cloud_connection === "ok"
                              ? "✓ Connected"
                              : "✗ Failed"}
                          </p>
                        </div>

                        <div>
                          <p className="text-xs text-muted-foreground">Orders Today</p>
                          <p className="mt-1 text-sm font-semibold text-card-foreground">
                            {safeNumber(centerDetail.orders_today, 0)}
                          </p>
                        </div>

                        <div>
                          <p className="text-xs text-muted-foreground">Success Rate</p>
                          <p className="mt-1 text-sm font-semibold text-card-foreground">
                            {safeNumber(centerDetail.success_rate, 0)}%
                          </p>
                        </div>

                        <div>
                          <p className="text-xs text-muted-foreground">Risk Score</p>
                          <p className="mt-1 text-sm font-semibold text-card-foreground">
                            {safeNumber(centerDetail.risk_score, 0)}%
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="replication" className="space-y-4">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <Activity className="h-4 w-4" />
                        MySQL Replication Status
                      </CardTitle>
                    </CardHeader>

                    <CardContent>
                      {centerDetail.replication ? (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                            <div className="rounded-lg bg-muted/30 p-4">
                              <p className="mb-1 text-xs text-muted-foreground">
                                Replica_IO_Running
                              </p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  centerDetail.replication.io_running === "Yes"
                                    ? "text-success"
                                    : "text-destructive"
                                )}
                              >
                                {safeText(centerDetail.replication.io_running)}
                              </p>
                            </div>

                            <div className="rounded-lg bg-muted/30 p-4">
                              <p className="mb-1 text-xs text-muted-foreground">
                                Replica_SQL_Running
                              </p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  centerDetail.replication.sql_running === "Yes"
                                    ? "text-success"
                                    : "text-destructive"
                                )}
                              >
                                {safeText(centerDetail.replication.sql_running)}
                              </p>
                            </div>

                            <div className="rounded-lg bg-muted/30 p-4">
                              <p className="mb-1 text-xs text-muted-foreground">
                                Seconds_Behind_Source
                              </p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  (centerDetail.replication.seconds_behind ?? 999) <= 5
                                    ? "text-success"
                                    : (centerDetail.replication.seconds_behind ?? 999) <= 30
                                    ? "text-warning"
                                    : "text-destructive"
                                )}
                              >
                                {centerDetail.replication.seconds_behind ?? "N/A"}
                              </p>
                            </div>
                          </div>

                          <div
                            className={cn(
                              "rounded-lg border p-4",
                              centerDetail.replication.io_running === "Yes" &&
                                centerDetail.replication.sql_running === "Yes" &&
                                (centerDetail.replication.seconds_behind ?? 999) <= 5
                                ? "border-success/30 bg-success/5"
                                : centerDetail.replication.io_running === "Yes" ||
                                  centerDetail.replication.sql_running === "Yes"
                                ? "border-warning/30 bg-warning/5"
                                : "border-destructive/30 bg-destructive/5"
                            )}
                          >
                            <p className="text-sm font-semibold">
                              {centerDetail.replication.io_running === "Yes" &&
                              centerDetail.replication.sql_running === "Yes" &&
                              (centerDetail.replication.seconds_behind ?? 999) <= 5
                                ? "✅ FULL SYNC — Replication is healthy"
                                : centerDetail.replication.io_running === "Yes" ||
                                  centerDetail.replication.sql_running === "Yes"
                                ? "⚠️ PARTIAL SYNC — Replication has issues"
                                : "🔴 OFFLINE — Replication is stopped"}
                            </p>
                          </div>

                          {(centerDetail.replication.last_io_error ||
                            centerDetail.replication.last_sql_error) && (
                            <div className="space-y-2">
                              {centerDetail.replication.last_io_error && (
                                <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3">
                                  <p className="mb-1 text-xs font-semibold text-destructive">
                                    Last IO Error
                                  </p>
                                  <p className="text-xs font-mono text-muted-foreground">
                                    {centerDetail.replication.last_io_error}
                                  </p>
                                </div>
                              )}

                              {centerDetail.replication.last_sql_error && (
                                <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3">
                                  <p className="mb-1 text-xs font-semibold text-destructive">
                                    Last SQL Error
                                  </p>
                                  <p className="text-xs font-mono text-muted-foreground">
                                    {centerDetail.replication.last_sql_error}
                                  </p>
                                </div>
                              )}
                            </div>
                          )}

                          <p className="text-xs text-muted-foreground">
                            Last checked: {formatDateTime(centerDetail.replication.checked_at)}
                          </p>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center py-8">
                          <Activity className="mb-2 h-8 w-8 text-muted-foreground/30" />
                          <p className="text-sm text-muted-foreground">
                            No replication data available for this server.
                          </p>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <History className="h-4 w-4" />
                        Replication History
                      </CardTitle>
                    </CardHeader>

                    <CardContent>
                      {replicationHistory.length > 0 ? (
                        <div className="space-y-4">
                          <ResponsiveContainer width="100%" height={250}>
                            <LineChart data={replicationHistory}>
                              <CartesianGrid
                                strokeDasharray="3 3"
                                stroke="hsl(var(--border))"
                              />
                              <XAxis
                                dataKey="checked_at"
                                tick={{ fontSize: 10 }}
                                stroke="hsl(var(--muted-foreground))"
                                tickFormatter={(v) => formatTimeOnly(v, "")}
                              />
                              <YAxis
                                tick={{ fontSize: 10 }}
                                stroke="hsl(var(--muted-foreground))"
                              />
                              <Tooltip
                                contentStyle={{ borderRadius: 8, fontSize: 12 }}
                                labelFormatter={(v) => formatDateTime(v)}
                              />
                              <Line
                                type="monotone"
                                dataKey="seconds_behind"
                                stroke="hsl(var(--primary))"
                                strokeWidth={2}
                                name="Lag (s)"
                                dot={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>

                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b bg-muted/40">
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    Time
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    IO
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    SQL
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    Lag
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    IO Error
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    SQL Error
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {replicationHistory.slice(0, 20).map((r: any, i: number) => (
                                  <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                                    <td className="p-2.5 text-muted-foreground">
                                      {formatDateTime(r.checked_at)}
                                    </td>
                                    <td className="p-2.5">
                                      <span
                                        className={cn(
                                          "font-semibold",
                                          r.io_running === "Yes"
                                            ? "text-success"
                                            : "text-destructive"
                                        )}
                                      >
                                        {r.io_running}
                                      </span>
                                    </td>
                                    <td className="p-2.5">
                                      <span
                                        className={cn(
                                          "font-semibold",
                                          r.sql_running === "Yes"
                                            ? "text-success"
                                            : "text-destructive"
                                        )}
                                      >
                                        {r.sql_running}
                                      </span>
                                    </td>
                                    <td className="p-2.5 font-mono">
                                      {r.seconds_behind ?? "—"}
                                    </td>
                                    <td className="max-w-[220px] truncate p-2.5 font-mono text-muted-foreground">
                                      {r.last_io_error || "—"}
                                    </td>
                                    <td className="max-w-[220px] truncate p-2.5 font-mono text-muted-foreground">
                                      {r.last_sql_error || "—"}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ) : (
                        <p className="py-8 text-center text-sm text-muted-foreground">
                          No replication history available.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="drift" className="space-y-4">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <AlertTriangle className="h-4 w-4 text-warning" />
                        Schema Drift Detection
                      </CardTitle>
                    </CardHeader>

                    <CardContent>
                      {driftReport ? (
                        <div className="space-y-4">
                          <div
                            className={cn(
                              "rounded-lg border p-4",
                              !centerDetail.drift_detected
                                ? "border-success/30 bg-success/5"
                                : "border-warning/30 bg-warning/5"
                            )}
                          >
                            <p className="text-sm font-semibold">
                              {!centerDetail.drift_detected
                                ? "✅ No drift detected — Schema matches expected baseline"
                                : "⚠️ Schema drift detected — Action required"}
                            </p>
                          </div>

                          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                            <div className="rounded-lg bg-muted/30 p-3">
                              <p className="text-xs text-muted-foreground">Missing Columns</p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  driftReport.missing_columns.length > 0
                                    ? "text-destructive"
                                    : "text-success"
                                )}
                              >
                                {driftReport.missing_columns.length}
                              </p>
                            </div>

                            <div className="rounded-lg bg-muted/30 p-3">
                              <p className="text-xs text-muted-foreground">Extra Columns</p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  driftReport.extra_columns.length > 0
                                    ? "text-warning"
                                    : "text-success"
                                )}
                              >
                                {driftReport.extra_columns.length}
                              </p>
                            </div>

                            <div className="rounded-lg bg-muted/30 p-3">
                              <p className="text-xs text-muted-foreground">Missing Rows</p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  driftReport.missing_rows > 0
                                    ? "text-destructive"
                                    : "text-success"
                                )}
                              >
                                {driftReport.missing_rows}
                              </p>
                            </div>

                            <div className="rounded-lg bg-muted/30 p-3">
                              <p className="text-xs text-muted-foreground">Incorrect FOSA ID</p>
                              <p
                                className={cn(
                                  "text-lg font-bold",
                                  driftReport.incorrect_fosaid
                                    ? "text-destructive"
                                    : "text-success"
                                )}
                              >
                                {driftReport.incorrect_fosaid ? "Yes" : "No"}
                              </p>
                            </div>
                          </div>

                          {driftReport.missing_columns.length > 0 && (
                            <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4">
                              <p className="mb-2 text-xs font-semibold text-destructive">
                                Missing Columns in `address` Table
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {driftReport.missing_columns.map((col) => (
                                  <Badge
                                    key={col}
                                    variant="secondary"
                                    className="bg-destructive/10 font-mono text-xs text-destructive"
                                  >
                                    {col}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}

                          {driftReport.extra_columns.length > 0 && (
                            <div className="rounded-lg border border-warning/20 bg-warning/5 p-4">
                              <p className="mb-2 text-xs font-semibold text-warning">
                                Extra Columns (not in baseline)
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {driftReport.extra_columns.map((col) => (
                                  <Badge
                                    key={col}
                                    variant="secondary"
                                    className="bg-warning/10 font-mono text-xs text-warning"
                                  >
                                    {col}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}

                          <p className="text-xs text-muted-foreground">
                            Last checked: {formatDateTime(driftReport.last_checked)} • Offline count:{" "}
                            {driftReport.offline_count}
                          </p>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center py-8">
                          <Shield className="mb-2 h-8 w-8 text-muted-foreground/30" />
                          <p className="text-sm text-muted-foreground">
                            No drift report available for this server.
                          </p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="metrics" className="space-y-4">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <BarChart3 className="h-4 w-4" />
                        Resource Metrics History
                      </CardTitle>
                    </CardHeader>

                    <CardContent>
                      {metricsHistory.length > 0 ? (
                        <div className="space-y-6">
                          <div>
                            <p className="mb-2 text-xs font-medium text-muted-foreground">
                              CPU / RAM / Disk Usage Over Time
                            </p>
                            <ResponsiveContainer width="100%" height={280}>
                              <AreaChart data={metricsHistory}>
                                <CartesianGrid
                                  strokeDasharray="3 3"
                                  stroke="hsl(var(--border))"
                                />
                                <XAxis
                                  dataKey="timestamp"
                                  tick={{ fontSize: 10 }}
                                  stroke="hsl(var(--muted-foreground))"
                                  tickFormatter={(v) => formatTimeOnly(v, "")}
                                />
                                <YAxis
                                  tick={{ fontSize: 10 }}
                                  stroke="hsl(var(--muted-foreground))"
                                  domain={[0, 100]}
                                />
                                <Tooltip
                                  contentStyle={{ borderRadius: 8, fontSize: 12 }}
                                  labelFormatter={(v) => formatDateTime(v)}
                                />
                                <Area
                                  type="monotone"
                                  dataKey="cpu_usage"
                                  stroke="hsl(var(--primary))"
                                  fill="hsl(var(--primary) / 0.15)"
                                  strokeWidth={2}
                                  name="CPU %"
                                />
                                <Area
                                  type="monotone"
                                  dataKey="ram_usage"
                                  stroke="hsl(var(--warning))"
                                  fill="hsl(var(--warning) / 0.15)"
                                  strokeWidth={2}
                                  name="RAM %"
                                />
                                <Area
                                  type="monotone"
                                  dataKey="disk_usage"
                                  stroke="hsl(var(--destructive))"
                                  fill="hsl(var(--destructive) / 0.1)"
                                  strokeWidth={2}
                                  name="Disk %"
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>

                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b bg-muted/40">
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    Time
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    CPU
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    RAM
                                  </th>
                                  <th className="p-2.5 text-left font-semibold text-muted-foreground">
                                    Disk
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {metricsHistory.slice(0, 20).map((m: any, i: number) => (
                                  <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                                    <td className="p-2.5 text-muted-foreground">
                                      {formatDateTime(m.timestamp)}
                                    </td>
                                    <td className="p-2.5">{safeNumber(m.cpu_usage)}%</td>
                                    <td className="p-2.5">{safeNumber(m.ram_usage)}%</td>
                                    <td className="p-2.5">{safeNumber(m.disk_usage)}%</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ) : (
                        <p className="py-8 text-center text-sm text-muted-foreground">
                          No metrics history available.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="timeline" className="space-y-4">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <Radio className="h-4 w-4 text-primary" />
                        Real Event Timeline
                      </CardTitle>
                    </CardHeader>

                    <CardContent>
                      {timeline.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-8">
                          <Radio className="mb-2 h-8 w-8 text-muted-foreground/30" />
                          <p className="text-sm text-muted-foreground">
                            No timeline events available yet.
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {timeline.map((event) => (
                            <div
                              key={event.id}
                              className={cn(
                                "flex items-start gap-3 rounded-lg border p-3",
                                event.severity === "critical"
                                  ? "border-destructive/20 bg-destructive/5"
                                  : event.severity === "warning"
                                  ? "border-warning/20 bg-warning/5"
                                  : "border-border bg-muted/30"
                              )}
                            >
                              <div className="mt-0.5">
                                {event.severity === "critical" ? (
                                  <XCircle className="h-4 w-4 text-destructive" />
                                ) : event.severity === "warning" ? (
                                  <AlertTriangle className="h-4 w-4 text-warning" />
                                ) : (
                                  <CheckCircle className="h-4 w-4 text-success" />
                                )}
                              </div>

                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  <Badge variant="outline" className="text-[10px]">
                                    {event.type}
                                  </Badge>
                                  <span className="text-[11px] text-muted-foreground">
                                    {formatDateTime(event.timestamp)}
                                  </span>
                                </div>
                                <p className="mt-1 text-sm text-card-foreground">
                                  {event.message}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default MonitoringPage;