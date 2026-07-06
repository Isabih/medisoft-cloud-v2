import { useQuery } from "@tanstack/react-query";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { fetchSmsLogs } from "@/lib/api";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  MessageSquare,
  AlertTriangle,
  Send,
} from "lucide-react";

interface SmsLog {
  id: string;
  to_number: string;
  sender?: string | null;
  recipient_role: "admin" | "head_of_center" | "other";
  center_id?: string | null;
  center_name?: string | null;
  message: string;
  status: "sent" | "delivered" | "failed" | "pending";
  provider_message_id?: string | null;
  error?: string | null;
  sent_at: string;
  delivered_at?: string | null;
}

const StatusBadge = ({ status }: { status: SmsLog["status"] }) => {
  const map = {
    sent: { cls: "bg-primary/15 text-primary", icon: Send, label: "Sent" },
    delivered: { cls: "bg-success/15 text-success", icon: CheckCircle2, label: "Delivered" },
    failed: { cls: "bg-destructive/15 text-destructive", icon: XCircle, label: "Failed" },
    pending: { cls: "bg-muted text-muted-foreground", icon: Loader2, label: "Pending" },
  };
  const { cls, icon: Icon, label } = map[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
};

const SmsLogsPage = () => {
  const { data: logs = [], isLoading } = useQuery<SmsLog[]>({
    queryKey: ["sms-logs"],
    queryFn: async () => (await fetchSmsLogs()).data,
    ...LIVE_QUERY_OPTIONS,
    refetchInterval: 15000,
  });

  const today = new Date().toISOString().slice(0, 10);
  const todayLogs = logs.filter((l) => l.sent_at.startsWith(today));
  const delivered = todayLogs.filter((l) => l.status === "delivered").length;
  const failed = todayLogs.filter((l) => l.status === "failed").length;

  return (
    <DashboardLayout>
      <PageHeader
        title="SMS Logs"
        subtitle="Africa's Talking gateway — outbound alerts to admins and health center heads"
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card><CardContent className="flex items-center gap-3 p-4">
          <MessageSquare className="h-5 w-5 text-primary" />
          <div><p className="text-xs text-muted-foreground">Total today</p><p className="text-xl font-bold">{todayLogs.length}</p></div>
        </CardContent></Card>
        <Card><CardContent className="flex items-center gap-3 p-4">
          <CheckCircle2 className="h-5 w-5 text-success" />
          <div><p className="text-xs text-muted-foreground">Delivered</p><p className="text-xl font-bold text-success">{delivered}</p></div>
        </CardContent></Card>
        <Card><CardContent className="flex items-center gap-3 p-4">
          <XCircle className="h-5 w-5 text-destructive" />
          <div><p className="text-xs text-muted-foreground">Failed</p><p className="text-xl font-bold text-destructive">{failed}</p></div>
        </CardContent></Card>
        <Card><CardContent className="flex items-center gap-3 p-4">
          <AlertTriangle className="h-5 w-5 text-warning" />
          <div><p className="text-xs text-muted-foreground">Delivery rate</p><p className="text-xl font-bold">{todayLogs.length ? Math.round((delivered/todayLogs.length)*100) : 0}%</p></div>
        </CardContent></Card>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center p-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40">
                  <th className="p-3 text-left font-semibold text-muted-foreground">Sent at</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Source (Sender)</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Destination</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Role</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Health Center</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Content</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Status</th>
                  <th className="p-3 text-left font-semibold text-muted-foreground">Delivered</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id} className="border-b last:border-0 hover:bg-muted/30 align-top">
                    <td className="p-3 text-xs text-muted-foreground whitespace-nowrap">{new Date(l.sent_at).toLocaleString()}</td>
                    <td className="p-3 font-mono text-xs">{l.sender || "MEDISOFT"}</td>
                    <td className="p-3 font-mono text-xs">{l.to_number}</td>
                    <td className="p-3"><Badge variant="outline" className="text-[10px]">{l.recipient_role}</Badge></td>
                    <td className="p-3 text-muted-foreground">{l.center_name || "—"}</td>
                    <td className="p-3 max-w-md text-xs whitespace-pre-wrap break-words" title={l.message}>{l.message}</td>
                    <td className="p-3"><StatusBadge status={l.status} /></td>
                    <td className="p-3 text-xs text-muted-foreground">{l.delivered_at ? new Date(l.delivered_at).toLocaleTimeString() : (l.error ? <span className="text-destructive">{l.error}</span> : "—")}</td>
                  </tr>
                ))}
                {!logs.length && (
                  <tr><td colSpan={8} className="p-8 text-center text-muted-foreground">No SMS sent yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default SmsLogsPage;
