import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader, StatusBadge } from "@/components/DashboardWidgets";
import { fetchHealthCenters, triggerAgentAction, fetchSmsLogs, resendSms } from "@/lib/api";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";
import { matchesHealthCenterQuery } from "@/lib/health-center-utils";
import { HealthCenter, PROVINCES_DISTRICTS, Province } from "@/lib/types";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  Search,
  Download,
  ExternalLink,
  Monitor,
  Copy,
  Wifi,
  WifiOff,
  CheckCircle,
  XCircle,
  HardDrive,
  Loader2,
  Phone,
  Database,
  Activity,
  RefreshCw,
  Power,
  MessageSquare,
  Stethoscope,
} from "lucide-react";
import { toast } from "sonner";
import { exportHealthCentersCSV, exportHealthCentersExcel } from "@/lib/export-utils";

const InternetBadge = ({ status }: { status: "online" | "offline" }) => {
  if (status === "online") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-success">
        <Wifi className="w-3 h-3" /> Online
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-destructive">
      <WifiOff className="w-3 h-3" /> Offline
    </span>
  );
};

const BackupBadge = ({ status }: { status?: "success" | "failed" | null }) => {
  if (!status) {
    return <span className="text-xs text-muted-foreground/50">—</span>;
  }

  if (status === "success") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-success">
        <CheckCircle className="w-3 h-3" /> Success
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-destructive">
      <XCircle className="w-3 h-3" /> Failed
    </span>
  );
};

const formatStorage = (value?: number | null) => {
  if (value == null || Number.isNaN(Number(value))) return "—";

  const size = Number(value);
  return size >= 1024 ? `${(size / 1024).toFixed(1)} GB` : `${size.toFixed(0)} MB`;
};

const formatLastActivity = (lastSeen?: string | null) => {
  if (!lastSeen) return "—";

  const lastActivity = new Date(lastSeen);
  if (Number.isNaN(lastActivity.getTime())) return "—";

  const diffMin = Math.floor((Date.now() - lastActivity.getTime()) / 60000);

  if (diffMin < 60) return `${diffMin} min ago`;
  return `${Math.floor(diffMin / 60)} hours ago`;
};

const HealthCentersPage = () => {
  const [search, setSearch] = useState("");
  const [province, setProvince] = useState<string>("all");
  const [district, setDistrict] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [busyId, setBusyId] = useState<string | null>(null);

  const { data: centers = [], isLoading, refetch } = useQuery<HealthCenter[]>({
    queryKey: ["health-centers"],
    queryFn: async () => (await fetchHealthCenters()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 30000,
  });

  const districts =
    province !== "all" ? PROVINCES_DISTRICTS[province as Province] || [] : [];

  const filtered = useMemo(() => {
    const q = search.toLowerCase();

    return centers.filter((c) => {
      if (search && !matchesHealthCenterQuery(c, q)) return false;
      if (province !== "all" && c.province !== province) return false;
      if (district !== "all" && c.district !== district) return false;
      if (status !== "all" && c.status !== status) return false;
      return true;
    });
  }, [centers, search, province, district, status]);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied!`);
  };

  const actionMut = useMutation({
    mutationFn: async (vars: { fossId: string; action: Parameters<typeof triggerAgentAction>[1]; label: string }) => {
      setBusyId(`${vars.fossId}:${vars.action}`);
      return (await triggerAgentAction(vars.fossId, vars.action)).data;
    },
    onSuccess: (_, vars) => {
      toast.success(`${vars.label} queued — agent will run it shortly`);
      setBusyId(null);
    },
    onError: (e: any, vars) => {
      toast.error(`${vars.label} failed: ${e?.response?.data?.detail || e?.message || "unknown error"}`);
      setBusyId(null);
    },
  });

  const retrySmsForCenter = async (centerId: string, centerName: string) => {
    try {
      setBusyId(`${centerId}:sms`);
      const logs = (await fetchSmsLogs({ center_id: centerId })).data as any[];
      const last = logs?.[0];
      if (!last) {
        toast.info(`No SMS history for ${centerName} yet`);
        return;
      }
      await resendSms(String(last.id));
      toast.success(`SMS resent to ${last.to_number}`);
    } catch (e: any) {
      toast.error(`Retry SMS failed: ${e?.response?.data?.detail || e?.message || "unknown"}`);
    } finally {
      setBusyId(null);
    }
  };

  const checkStatus = async () => {
    await refetch();
    toast.success("Status refreshed");
  };

  return (
    <DashboardLayout>
      <PageHeader title="Health Centers" subtitle="Monitor all registered health centers">
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={checkStatus}>
            <RefreshCw className="mr-1 h-4 w-4" />
            Check status
          </Button>
          <Link to="/health-centers/register">
            <Button size="sm" className="gradient-primary text-primary-foreground">
              + Register
            </Button>
          </Link>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              exportHealthCentersCSV(filtered);
              toast.success("CSV downloaded");
            }}
          >
            <Download className="mr-1 h-4 w-4" />
            CSV
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              exportHealthCentersExcel(filtered);
              toast.success("Excel downloaded");
            }}
          >
            <Download className="mr-1 h-4 w-4" />
            Excel
          </Button>
        </div>
      </PageHeader>

      <div className="mb-6 flex flex-wrap gap-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by name, database, FOSA ID, province, district..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        <Select
          value={province}
          onValueChange={(v) => {
            setProvince(v);
            setDistrict("all");
          }}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Province" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Provinces</SelectItem>
            {Object.keys(PROVINCES_DISTRICTS).map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={district}
          onValueChange={setDistrict}
          disabled={province === "all"}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="District" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Districts</SelectItem>
            {districts.map((d) => (
              <SelectItem key={d} value={d}>
                {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="online">Online</SelectItem>
            <SelectItem value="offline">Offline</SelectItem>
            <SelectItem value="partial">Partial</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="p-3 text-left font-semibold text-muted-foreground">HC Name</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">FOSS ID</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Status</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Internet</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">MySQL</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">IO</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">SQL</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">DB Size</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Head of HC</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">AnyDesk</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">RustDesk</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Last Seen</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Last Updated</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Backup</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Action</th>
                </tr>
              </thead>

              <tbody>
                {filtered.map((c) => {
                  const activityLabel = formatLastActivity(c.last_seen);
                  const updatedLabel = formatLastActivity(c.last_sync);
                  const ioOk = (c.replication?.io_running || "").toLowerCase() === "yes";
                  const sqlOk = (c.replication?.sql_running || "").toLowerCase() === "yes";
                  const mysqlOk = c.mysql_status === "online";

                  return (
                    <tr
                      key={c.id}
                      className="border-b transition-colors last:border-0 hover:bg-muted/30"
                    >
                      <td className="p-3 font-medium text-card-foreground">{c.name || "—"}</td>
                      <td className="p-3 font-mono text-xs text-muted-foreground">{c.foss_id || "—"}</td>
                      <td className="p-3">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="p-3">
                        <InternetBadge status={c.internet_status} />
                      </td>
                      <td className="p-3">
                        <span className={`inline-flex items-center gap-1 text-xs font-semibold ${mysqlOk ? "text-success" : "text-destructive"}`}>
                          <Database className="h-3 w-3" /> {mysqlOk ? "Online" : "Offline"}
                        </span>
                      </td>
                      <td className="p-3">
                        {c.replication ? (
                          <span className={`inline-flex items-center gap-1 text-xs font-semibold ${ioOk ? "text-success" : "text-destructive"}`}>
                            {ioOk ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                            {c.replication.io_running || "?"}
                          </span>
                        ) : <span className="text-xs text-muted-foreground/50">—</span>}
                      </td>
                      <td className="p-3">
                        {c.replication ? (
                          <span className={`inline-flex items-center gap-1 text-xs font-semibold ${sqlOk ? "text-success" : "text-destructive"}`}>
                            {sqlOk ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                            {c.replication.sql_running || "?"}
                          </span>
                        ) : <span className="text-xs text-muted-foreground/50">—</span>}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <HardDrive className="h-3 w-3" />
                          {formatStorage(c.data_size_mb)}
                        </span>
                      </td>
                      <td className="p-3 text-xs">
                        {c.phone_number_1 ? (
                          <button
                            onClick={() => copyToClipboard(c.phone_number_1!, "Head phone")}
                            className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-card-foreground"
                            title="Click to copy"
                          >
                            <Phone className="h-3 w-3" />
                            <span>
                              {c.phone_contact_1 || "Head"}: <span className="font-mono">{c.phone_number_1}</span>
                            </span>
                          </button>
                        ) : (
                          <span className="text-xs text-muted-foreground/50">—</span>
                        )}
                      </td>
                      <td className="p-3">
                        {c.anydesk_id ? (
                          <button
                            onClick={() => copyToClipboard(c.anydesk_id!, "AnyDesk ID")}
                            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-card-foreground"
                            title="Click to copy"
                          >
                            <Monitor className="h-3 w-3" />
                            <span className="font-mono">{c.anydesk_id}</span>
                            <Copy className="h-3 w-3 opacity-50" />
                          </button>
                        ) : (
                          <span className="text-xs text-muted-foreground/50">—</span>
                        )}
                      </td>
                      <td className="p-3">
                        {c.rustdesk_id ? (
                          <button
                            onClick={() => copyToClipboard(c.rustdesk_id!, "RustDesk ID")}
                            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-card-foreground"
                            title="Click to copy"
                          >
                            <Monitor className="h-3 w-3" />
                            <span className="font-mono">{c.rustdesk_id}</span>
                            <Copy className="h-3 w-3 opacity-50" />
                          </button>
                        ) : (
                          <span className="text-xs text-muted-foreground/50">—</span>
                        )}
                      </td>
                      <td className="p-3 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <Activity className="h-3 w-3" /> {activityLabel}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-muted-foreground">{updatedLabel}</td>
                      <td className="p-3">
                        <BackupBadge status={c.last_backup?.status} />
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            disabled={!c.foss_id || busyId === `${c.foss_id}:restart-replica`}
                            onClick={() => c.foss_id && actionMut.mutate({ fossId: c.foss_id, action: "restart-replica", label: "Resync" })}
                            title="Trigger replication resync"
                          >
                            {busyId === `${c.foss_id}:restart-replica` ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                            <span className="ml-1 hidden xl:inline">Resync</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            disabled={!c.foss_id || busyId === `${c.foss_id}:restart-mysql`}
                            onClick={() => c.foss_id && actionMut.mutate({ fossId: c.foss_id, action: "restart-mysql", label: "Restart MySQL" })}
                            title="Restart MySQL"
                          >
                            {busyId === `${c.foss_id}:restart-mysql` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Power className="h-3 w-3" />}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            disabled={busyId === `${c.id}:sms`}
                            onClick={() => retrySmsForCenter(c.id, c.name)}
                            title="Retry latest SMS to head of HC"
                          >
                            {busyId === `${c.id}:sms` ? <Loader2 className="h-3 w-3 animate-spin" /> : <MessageSquare className="h-3 w-3" />}
                          </Button>
                          <Link to={`/health-centers/${c.id}`} title="Open detail / actions">
                            <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                              <ExternalLink className="h-3.5 w-3.5" />
                            </Button>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}

                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={15} className="p-8 text-center text-muted-foreground">
                      No health centers found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default HealthCentersPage;