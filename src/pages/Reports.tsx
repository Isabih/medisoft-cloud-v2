import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { fetchDailyReports, fetchHealthCenters, fetchBackups, fetchOperationalReport, fetchIncidentHistory } from "@/lib/api";
import { HealthCenter, DailyReport, BackupRecord, CenterDailyStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Download, FileText, ChevronDown, ChevronUp, CheckCircle, XCircle, HardDrive, Loader2, MessageSquare, ShieldAlert } from "lucide-react";
import React from "react";
import { exportReportsCSV, exportReportsExcel, exportReportsPDF, exportOperationalCSV, exportOperationalExcel, OperationalRow } from "@/lib/export-utils";

const SyncStatusBadge = ({ status }: { status: "full" | "partial" | "none" }) => {
  const map = {
    full: { label: "Full Sync", cls: "bg-success/15 text-success border-success/30" },
    partial: { label: "Partial", cls: "bg-warning/15 text-warning border-warning/30" },
    none: { label: "No Data", cls: "bg-destructive/15 text-destructive border-destructive/30" },
  };
  const { label, cls } = map[status];
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>{label}</span>;
};

const BackupStatusBadge = ({ status }: { status: "success" | "failed" }) => {
  if (status === "success") return <span className="inline-flex items-center gap-1 text-xs font-semibold text-success"><CheckCircle className="w-3 h-3" /> Success</span>;
  return <span className="inline-flex items-center gap-1 text-xs font-semibold text-destructive"><XCircle className="w-3 h-3" /> Failed</span>;
};

const ReportsPage = () => {
  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [centerFilter, setCenterFilter] = useState<string>("all");
  const [reportView, setReportView] = useState<"daily" | "by-center" | "backups" | "operational" | "incidents">("operational");
  const [backupCenterFilter, setBackupCenterFilter] = useState<string>("all");
  const [opFrom, setOpFrom] = useState<string>(() => {
    const d = new Date(); d.setDate(d.getDate() - 7);
    return d.toISOString().split("T")[0];
  });
  const [opTo, setOpTo] = useState<string>(() => new Date().toISOString().split("T")[0]);
  const [opOnly, setOpOnly] = useState<"all" | "issues">("all");
  const [opProvince, setOpProvince] = useState<string>("all");
  const [opDistrict, setOpDistrict] = useState<string>("all");
  const [opStatus, setOpStatus] = useState<string>("all");
  const [opConfirmed, setOpConfirmed] = useState(false);
  const [incidentFrom, setIncidentFrom] = useState<string>(() => { const d = new Date(); d.setDate(d.getDate() - 90); return d.toISOString().split("T")[0]; });
  const [incidentTo, setIncidentTo] = useState<string>(() => new Date().toISOString().split("T")[0]);

  const { data: dailyReports = [], isLoading: loadingReports } = useQuery<DailyReport[]>({
    queryKey: ["daily-reports"],
    queryFn: async () => (await fetchDailyReports()).data,
  });

  const { data: centers = [] } = useQuery<HealthCenter[]>({
    queryKey: ["health-centers"],
    queryFn: async () => (await fetchHealthCenters()).data,
  });

  const { data: allBackups = [] } = useQuery<BackupRecord[]>({
    queryKey: ["backups"],
    queryFn: async () => (await fetchBackups()).data,
  });

  const { data: opRows = [], isLoading: loadingOp } = useQuery<OperationalRow[]>({
    queryKey: ["operational-report", opFrom, opTo],
    queryFn: async () => (await fetchOperationalReport({ from: opFrom, to: opTo })).data,
  });

  const { data: incidentRows = [], isLoading: loadingIncidents } = useQuery<any[]>({
    queryKey: ["incident-history", incidentFrom, incidentTo],
    queryFn: async () => (await fetchIncidentHistory({ from: incidentFrom, to: incidentTo, limit: 1000 })).data,
    enabled: reportView === "incidents",
  });

  // index of centers by id for join (province/district/status filters)
  const centersById = React.useMemo(() => {
    const m = new Map<string, HealthCenter>();
    centers.forEach((c) => m.set(c.id, c));
    return m;
  }, [centers]);

  const districtsForProvince = React.useMemo(() => {
    if (opProvince === "all") return [];
    const set = new Set<string>();
    centers.forEach((c) => { if (c.province === opProvince && c.district) set.add(c.district); });
    return Array.from(set).sort();
  }, [centers, opProvince]);

  const filteredOp = React.useMemo(() => {
    return opRows.filter((r) => {
      const c = centersById.get(r.center_id);
      if (opProvince !== "all" && c?.province !== opProvince) return false;
      if (opDistrict !== "all" && c?.district !== opDistrict) return false;
      if (opStatus !== "all" && c?.status !== opStatus) return false;
      if (opOnly === "issues" && !(r.io_down || r.sql_down || r.outdated || !r.head_notified)) return false;
      return true;
    });
  }, [opRows, opOnly, opProvince, opDistrict, opStatus, centersById]);

  // Reset confirmation whenever filters change
  React.useEffect(() => { setOpConfirmed(false); }, [opFrom, opTo, opOnly, opProvince, opDistrict, opStatus]);


  const toggleExpand = (date: string) => {
    setExpandedDate(expandedDate === date ? null : date);
    setCenterFilter("all");
  };

  const filterDetails = (details?: CenterDailyStatus[]) => {
    if (!details) return [];
    if (centerFilter === "all") return details;
    return details.filter(d => d.sync_status === centerFilter);
  };

  const centerSummary = React.useMemo(() => {
    const map = new Map<string, { name: string; full: number; partial: number; none: number; totalRows: number; totalMb: number; days: number }>();
    dailyReports.forEach(r => {
      r.center_details?.forEach(cd => {
        const existing = map.get(cd.center_id) || { name: cd.center_name, full: 0, partial: 0, none: 0, totalRows: 0, totalMb: 0, days: 0 };
        existing.days++;
        if (cd.sync_status === "full") existing.full++;
        else if (cd.sync_status === "partial") existing.partial++;
        else existing.none++;
        existing.totalRows += cd.rows_synced;
        existing.totalMb += cd.data_volume_mb;
        map.set(cd.center_id, existing);
      });
    });
    return Array.from(map.entries()).map(([id, data]) => ({ id, ...data }));
  }, [dailyReports]);

  const backupsByDate = React.useMemo(() => {
    let filtered = allBackups;
    if (backupCenterFilter !== "all") {
      filtered = filtered.filter(b => b.center_id === backupCenterFilter);
    }
    const grouped = new Map<string, typeof filtered>();
    filtered.forEach(b => {
      const arr = grouped.get(b.date) || [];
      arr.push(b);
      grouped.set(b.date, arr);
    });
    return Array.from(grouped.entries()).sort(([a], [b]) => b.localeCompare(a));
  }, [allBackups, backupCenterFilter]);

  if (loadingReports) {
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
      <PageHeader title="Reports" subtitle="Daily auto-generated sync & operational reports">
        <div className="flex flex-wrap gap-2">
          <Select value={reportView} onValueChange={(v) => setReportView(v as any)}>
            <SelectTrigger className="w-[200px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="operational">Operational (IO/SQL/SMS)</SelectItem>
              <SelectItem value="incidents">Incident History</SelectItem>
              <SelectItem value="daily">Daily Overview</SelectItem>
              <SelectItem value="by-center">By Health Center</SelectItem>
              <SelectItem value="backups">Nightly Backups</SelectItem>
            </SelectContent>
          </Select>
          {reportView === "operational" ? (
            <>
              <Button variant="outline" size="sm" disabled={!opConfirmed} onClick={() => exportOperationalCSV(filteredOp)}><Download className="w-4 h-4 mr-1" />CSV</Button>
              <Button variant="outline" size="sm" disabled={!opConfirmed} onClick={() => exportOperationalExcel(filteredOp)}><Download className="w-4 h-4 mr-1" />Excel</Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={() => { exportReportsPDF(dailyReports); }}><Download className="w-4 h-4 mr-1" />PDF</Button>
              <Button variant="outline" size="sm" onClick={() => { exportReportsExcel(dailyReports); }}><Download className="w-4 h-4 mr-1" />Excel</Button>
            </>
          )}
        </div>
      </PageHeader>

      {reportView === "incidents" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">From</label>
              <Input type="date" value={incidentFrom} onChange={(e) => setIncidentFrom(e.target.value)} className="w-[160px] h-9" />
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">To</label>
              <Input type="date" value={incidentTo} onChange={(e) => setIncidentTo(e.target.value)} className="w-[160px] h-9" />
            </div>
            <Badge variant="secondary" className="h-9 px-3">{incidentRows.length} incidents</Badge>
          </div>
          <div className="rounded-xl border bg-card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="text-left p-3">Time</th>
                  <th className="text-left p-3">Health Centre</th>
                  <th className="text-left p-3">Channel</th>
                  <th className="text-left p-3">Event</th>
                  <th className="text-left p-3">Count</th>
                  <th className="text-left p-3">Cause / Fix</th>
                </tr>
              </thead>
              <tbody>
                {loadingIncidents ? (
                  <tr><td colSpan={6} className="p-6 text-center text-muted-foreground">Loading incident history...</td></tr>
                ) : incidentRows.length === 0 ? (
                  <tr><td colSpan={6} className="p-6 text-center text-muted-foreground">No incidents found for this range.</td></tr>
                ) : incidentRows.map((r: any) => (
                  <tr key={r.id} className="border-t align-top">
                    <td className="p-3 whitespace-nowrap">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</td>
                    <td className="p-3">{r.center_name || r.foss_id || r.center_id || "Unknown"}</td>
                    <td className="p-3">{r.channel_name || "—"}</td>
                    <td className="p-3"><Badge variant={r.severity === "critical" ? "destructive" : "secondary"}>{r.event_type}</Badge></td>
                    <td className="p-3">{r.occurrence_count ?? 1}</td>
                    <td className="p-3 max-w-xl">
                      <p className="font-medium">{r.root_cause || "Operational issue detected."}</p>
                      <p className="text-xs text-muted-foreground mt-1">{r.recommended_fix || "Review the health centre detail page and timeline."}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : reportView === "operational" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">From</label>
              <Input type="date" value={opFrom} onChange={(e) => setOpFrom(e.target.value)} className="w-[160px] h-9" />
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">To</label>
              <Input type="date" value={opTo} onChange={(e) => setOpTo(e.target.value)} className="w-[160px] h-9" />
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Province</label>
              <Select value={opProvince} onValueChange={(v) => { setOpProvince(v); setOpDistrict("all"); }}>
                <SelectTrigger className="h-9 w-[160px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Provinces</SelectItem>
                  {Array.from(new Set(centers.map(c => c.province).filter(Boolean))).sort().map(p => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">District</label>
              <Select value={opDistrict} onValueChange={setOpDistrict} disabled={opProvince === "all"}>
                <SelectTrigger className="h-9 w-[160px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Districts</SelectItem>
                  {districtsForProvince.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Status</label>
              <Select value={opStatus} onValueChange={setOpStatus}>
                <SelectTrigger className="h-9 w-[140px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="online">Online</SelectItem>
                  <SelectItem value="partial">Partial</SelectItem>
                  <SelectItem value="offline">Offline</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-1">
              {(["all","issues"] as const).map(f => (
                <Button key={f} size="sm" variant={opOnly === f ? "default" : "outline"} onClick={() => setOpOnly(f)} className="h-9">
                  {f === "all" ? "All rows" : "Issues only"}
                </Button>
              ))}
            </div>
            <div className="text-xs text-muted-foreground ml-auto">
              {filteredOp.length} row{filteredOp.length === 1 ? "" : "s"}
            </div>
          </div>

          {/* Export preview */}
          <div className="rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">Export preview — confirm before download</h3>
                <p className="text-xs text-muted-foreground">
                  Range <span className="font-mono">{opFrom}</span> → <span className="font-mono">{opTo}</span>
                  {" · "}Province: <b>{opProvince === "all" ? "All" : opProvince}</b>
                  {" · "}District: <b>{opDistrict === "all" ? "All" : opDistrict}</b>
                  {" · "}Status: <b>{opStatus === "all" ? "All" : opStatus}</b>
                  {" · "}Rows: <b>{opOnly === "all" ? "All" : "Issues only"}</b>
                  {" · "}{filteredOp.length} rows · {new Set(filteredOp.map(r => r.center_id)).size} health centers
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border bg-card px-2 py-1 text-xs">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5"
                    checked={opConfirmed}
                    onChange={(e) => setOpConfirmed(e.target.checked)}
                  />
                  I confirm the centers/range above
                </label>
                <Button size="sm" variant="default" disabled={!opConfirmed || filteredOp.length === 0} onClick={() => exportOperationalCSV(filteredOp)}>
                  <Download className="w-4 h-4 mr-1" />Download CSV
                </Button>
                <Button size="sm" variant="outline" disabled={!opConfirmed || filteredOp.length === 0} onClick={() => exportOperationalExcel(filteredOp)}>
                  <Download className="w-4 h-4 mr-1" />Download Excel
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4 md:grid-cols-6">
              {Array.from(new Map(filteredOp.map(r => [r.center_id, r])).values())
                .slice(0, 60)
                .map((r) => {
                  const bad = r.both_down || r.io_down || r.sql_down || r.outdated;
                  return (
                    <div
                      key={r.center_id}
                      className={`flex items-center gap-1.5 truncate rounded-md border px-2 py-1 ${
                        bad ? "border-destructive/40 bg-destructive/5" : "border-success/30 bg-success/5"
                      }`}
                      title={`${r.center_name} · ${r.foss_id}`}
                    >
                      {bad ? <XCircle className="h-3 w-3 shrink-0 text-destructive" /> : <CheckCircle className="h-3 w-3 shrink-0 text-success" />}
                      <span className="truncate">{r.center_name}</span>
                    </div>
                  );
                })}
              {new Set(filteredOp.map(r => r.center_id)).size > 60 && (
                <div className="col-span-2 rounded-md border bg-muted/40 px-2 py-1 text-muted-foreground sm:col-span-4 md:col-span-6">
                  + {new Set(filteredOp.map(r => r.center_id)).size - 60} more…
                </div>
              )}
              {filteredOp.length === 0 && (
                <div className="col-span-2 rounded-md border bg-muted/30 px-2 py-2 text-center text-muted-foreground sm:col-span-4 md:col-span-6">
                  Nothing to export for this range.
                </div>
              )}
            </div>
          </div>



          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="p-3">Day</th>
                    <th className="p-3">Health Center</th>
                    <th className="p-3">Head of HC</th>
                    <th className="p-3">Last Seen</th>
                    <th className="p-3">IO</th>
                    <th className="p-3">SQL</th>
                    <th className="p-3">State</th>
                    <th className="p-3">SMS Sent</th>
                    <th className="p-3">Delivered</th>
                    <th className="p-3">Head notified</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingOp && filteredOp.length === 0 ? (
                    <tr><td colSpan={10} className="text-center p-8"><Loader2 className="w-5 h-5 animate-spin inline" /></td></tr>
                  ) : filteredOp.length === 0 ? (
                    <tr><td colSpan={10} className="text-center p-8 text-muted-foreground">No data for this range.</td></tr>
                  ) : filteredOp.map((r, i) => {
                    const state = r.both_down ? { label: "BOTH DOWN", cls: "bg-destructive text-destructive-foreground" }
                      : r.io_down ? { label: "IO DOWN", cls: "bg-destructive/20 text-destructive border border-destructive/40" }
                      : r.sql_down ? { label: "SQL DOWN", cls: "bg-warning/20 text-warning border border-warning/40" }
                      : r.outdated ? { label: "OUTDATED", cls: "bg-muted text-muted-foreground border" }
                      : { label: "OK", cls: "bg-success/15 text-success border border-success/30" };
                    return (
                      <tr key={i} className="border-b last:border-0 hover:bg-muted/20 transition-colors">
                        <td className="p-3 text-muted-foreground font-mono text-xs">{r.day}</td>
                        <td className="p-3 font-medium">{r.center_name}<div className="text-[10px] text-muted-foreground font-mono">{r.foss_id}</div></td>
                        <td className="p-3 text-xs">
                          <div>{r.head_name || <span className="text-muted-foreground">—</span>}</div>
                          <div className="text-muted-foreground font-mono">{r.head_phone || ""}</div>
                        </td>
                        <td className="p-3 text-xs text-muted-foreground font-mono">{r.last_seen ? new Date(r.last_seen).toLocaleString() : "—"}</td>
                        <td className="p-3">{r.io_down ? <XCircle className="w-4 h-4 text-destructive" /> : <CheckCircle className="w-4 h-4 text-success" />}</td>
                        <td className="p-3">{r.sql_down ? <XCircle className="w-4 h-4 text-destructive" /> : <CheckCircle className="w-4 h-4 text-success" />}</td>
                        <td className="p-3"><span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${state.cls}`}>{r.both_down && <ShieldAlert className="w-3 h-3" />}{state.label}</span></td>
                        <td className="p-3 text-xs"><Badge variant="outline" className="gap-1"><MessageSquare className="w-3 h-3" />{r.sms_sent}</Badge></td>
                        <td className="p-3 text-xs">{r.sms_delivered}/{r.sms_sent}</td>
                        <td className="p-3">{r.head_notified ? <Badge variant="default" className="gap-1"><CheckCircle className="w-3 h-3" />Yes</Badge> : <Badge variant="destructive" className="gap-1"><XCircle className="w-3 h-3" />No</Badge>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : reportView === "backups" ? (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <HardDrive className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Filter by center:</span>
            <Select value={backupCenterFilter} onValueChange={setBackupCenterFilter}>
              <SelectTrigger className="w-[220px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Health Centers</SelectItem>
                {centers.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-semibold text-muted-foreground">Date</th>
                    <th className="text-left p-3 font-semibold text-muted-foreground">HC Name</th>
                    <th className="text-left p-3 font-semibold text-muted-foreground">Time</th>
                    <th className="text-left p-3 font-semibold text-muted-foreground">File Name</th>
                    <th className="text-left p-3 font-semibold text-muted-foreground">Size</th>
                    <th className="text-left p-3 font-semibold text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {backupsByDate.map(([date, records]) => (
                    <React.Fragment key={date}>
                      <tr className="bg-muted/30">
                        <td colSpan={6} className="p-2 px-3 text-xs font-bold text-muted-foreground uppercase tracking-wider">
                          {date} — {records.filter(r => r.status === "success").length}/{records.length} Successful
                        </td>
                      </tr>
                      {records.map(b => (
                        <tr key={b.id} className="border-b last:border-0 hover:bg-muted/20 transition-colors">
                          <td className="p-3 text-muted-foreground">{b.date}</td>
                          <td className="p-3 font-medium text-card-foreground">{b.center_name}</td>
                          <td className="p-3 text-muted-foreground">{b.time}</td>
                          <td className="p-3 font-mono text-xs text-muted-foreground">{b.file_name}</td>
                          <td className="p-3 text-muted-foreground">{b.file_size_mb > 0 ? `${b.file_size_mb} MB` : "—"}</td>
                          <td className="p-3"><BackupStatusBadge status={b.status} /></td>
                        </tr>
                      ))}
                    </React.Fragment>
                  ))}
                  {backupsByDate.length === 0 && (
                    <tr><td colSpan={6} className="text-center p-8 text-muted-foreground">No backup records found.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-3">* Dumps older than 7 days are automatically deleted from the server.</p>
        </div>
      ) : reportView === "by-center" ? (
        <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-semibold text-muted-foreground">Health Center</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Days Tracked</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Full Sync</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Partial</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">No Data</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Total Rows</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Total Data (MB)</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Sync Rate</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Backup</th>
                </tr>
              </thead>
              <tbody>
                {centerSummary.map(c => {
                  const rate = c.days > 0 ? ((c.full / c.days) * 100).toFixed(1) : "0";
                  const rateNum = parseFloat(rate);
                  const rateColor = rateNum >= 90 ? "text-success" : rateNum >= 60 ? "text-warning" : "text-destructive";
                  const hc = centers.find(h => h.id === c.id);
                  return (
                    <tr key={c.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="p-3 font-medium text-card-foreground">{c.name}</td>
                      <td className="p-3 text-muted-foreground">{c.days}</td>
                      <td className="p-3"><span className="text-success font-semibold">{c.full}</span></td>
                      <td className="p-3"><span className="text-warning font-semibold">{c.partial}</span></td>
                      <td className="p-3"><span className="text-destructive font-semibold">{c.none}</span></td>
                      <td className="p-3 text-muted-foreground">{c.totalRows.toLocaleString()}</td>
                      <td className="p-3 text-muted-foreground">{c.totalMb.toFixed(1)}</td>
                      <td className="p-3"><span className={`font-bold ${rateColor}`}>{rate}%</span></td>
                      <td className="p-3">
                        {hc?.last_backup ? <BackupStatusBadge status={hc.last_backup.status} /> : <span className="text-xs text-muted-foreground/50">—</span>}
                      </td>
                    </tr>
                  );
                })}
                {centerSummary.length === 0 && (
                  <tr><td colSpan={9} className="text-center p-8 text-muted-foreground">No data available.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-semibold text-muted-foreground w-8"></th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Date</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Full Sync</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Partial</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">No Data</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Volume (GB)</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Rows Synced</th>
                  <th className="text-left p-3 font-semibold text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {dailyReports.map((r) => (
                  <React.Fragment key={r.date}>
                    <tr className="border-b last:border-0 hover:bg-muted/30 transition-colors cursor-pointer" onClick={() => toggleExpand(r.date)}>
                      <td className="p-3">
                        {expandedDate === r.date ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                      </td>
                      <td className="p-3 font-medium text-card-foreground">{r.date}</td>
                      <td className="p-3"><span className="text-success font-semibold">{r.full_sync_centers}</span></td>
                      <td className="p-3"><span className="text-warning font-semibold">{r.partial_centers}</span></td>
                      <td className="p-3"><span className="text-destructive font-semibold">{r.no_data_centers}</span></td>
                      <td className="p-3 text-muted-foreground">{r.total_data_volume_gb}</td>
                      <td className="p-3 text-muted-foreground">{r.total_rows_synced.toLocaleString()}</td>
                      <td className="p-3">
                        <Button variant="ghost" size="sm" onClick={(e) => e.stopPropagation()}><FileText className="w-3.5 h-3.5" /></Button>
                      </td>
                    </tr>
                    {expandedDate === r.date && (
                      <tr>
                        <td colSpan={8} className="p-0">
                          <div className="bg-muted/20 border-t px-6 py-4">
                            <div className="flex items-center justify-between mb-3">
                              <h4 className="text-sm font-semibold text-card-foreground">Health Center Sync Details — {r.date}</h4>
                              <div className="flex gap-1">
                                {(["all", "full", "partial", "none"] as const).map(f => (
                                  <Button
                                    key={f}
                                    variant={centerFilter === f ? "default" : "outline"}
                                    size="sm"
                                    className="text-xs h-7"
                                    onClick={() => setCenterFilter(f)}
                                  >
                                    {f === "all" ? "All" : f === "full" ? "Full Sync" : f === "partial" ? "Partial" : "No Data"}
                                  </Button>
                                ))}
                              </div>
                            </div>
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b">
                                  <th className="text-left p-2 font-semibold text-muted-foreground">Health Center</th>
                                  <th className="text-left p-2 font-semibold text-muted-foreground">Status</th>
                                  <th className="text-left p-2 font-semibold text-muted-foreground">Rows Synced</th>
                                  <th className="text-left p-2 font-semibold text-muted-foreground">Data (MB)</th>
                                  <th className="text-left p-2 font-semibold text-muted-foreground">Last Sync</th>
                                </tr>
                              </thead>
                              <tbody>
                                {filterDetails(r.center_details).map(cd => (
                                  <tr key={cd.center_id} className="border-b last:border-0">
                                    <td className="p-2 font-medium text-card-foreground">{cd.center_name}</td>
                                    <td className="p-2"><SyncStatusBadge status={cd.sync_status} /></td>
                                    <td className="p-2 text-muted-foreground">{cd.rows_synced.toLocaleString()}</td>
                                    <td className="p-2 text-muted-foreground">{cd.data_volume_mb}</td>
                                    <td className="p-2 text-muted-foreground">{cd.last_sync_time ? new Date(cd.last_sync_time).toLocaleTimeString() : "—"}</td>
                                  </tr>
                                ))}
                                {filterDetails(r.center_details).length === 0 && (
                                  <tr><td colSpan={5} className="text-center p-4 text-muted-foreground">No centers match this filter.</td></tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {dailyReports.length === 0 && (
                  <tr><td colSpan={8} className="text-center p-8 text-muted-foreground">No reports available.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default ReportsPage;
