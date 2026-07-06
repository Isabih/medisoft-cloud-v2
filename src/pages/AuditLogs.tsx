import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  History,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Filter,
  RefreshCw,
} from "lucide-react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchAuditLogs } from "@/lib/api";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";

type LogRow = {
  id: number;
  action: string;
  target_type: string | null;
  target_id: string | null;
  target_name: string | null;
  actor: string | null;
  outcome: "success" | "failure" | "pending";
  details: string | null;
  created_at: string;
};

const OutcomeIcon = ({ o }: { o: LogRow["outcome"] }) => {
  if (o === "success") return <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-label="success" />;
  if (o === "failure") return <XCircle className="h-3.5 w-3.5 text-destructive" aria-label="failure" />;
  return <Clock className="h-3.5 w-3.5 text-warning" aria-label="pending" />;
};

export default function AuditLogsPage() {
  const [outcome, setOutcome] = useState<string>("all");
  const [search, setSearch] = useState("");

  const { data: rows = [], isFetching, refetch } = useQuery<LogRow[]>({
    queryKey: ["audit-logs", outcome],
    queryFn: async () =>
      (
        await fetchAuditLogs(
          outcome === "all" ? { limit: 500 } : { outcome, limit: 500 },
        )
      ).data,
    refetchInterval: 30_000,
    ...LIVE_QUERY_OPTIONS,
  });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.action.toLowerCase().includes(q) ||
        (r.target_name || "").toLowerCase().includes(q) ||
        (r.target_id || "").toLowerCase().includes(q) ||
        (r.actor || "").toLowerCase().includes(q) ||
        (r.details || "").toLowerCase().includes(q),
    );
  }, [rows, search]);

  return (
    <DashboardLayout>
      <PageHeader
        title="Audit Log"
        subtitle="Every triggered action — resync, SMS, backup updates — with timestamp, actor and outcome."
      >
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          <RefreshCw className={`mr-1 h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </PageHeader>

      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search action, target, user, details…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-9 max-w-sm"
            />
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger className="h-9 w-[140px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All outcomes</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="failure">Failure</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
              </SelectContent>
            </Select>
            <span className="ml-auto text-xs text-muted-foreground">
              {filtered.length} entries
            </span>
          </div>

          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-3">When</th>
                  <th className="p-3">Action</th>
                  <th className="p-3">Target</th>
                  <th className="p-3">Actor</th>
                  <th className="p-3">Outcome</th>
                  <th className="p-3">Details</th>
                </tr>
              </thead>
              <tbody>
                {isFetching && rows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center">
                      <Loader2 className="inline h-5 w-5 animate-spin text-muted-foreground" />
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-muted-foreground">
                      <History className="mx-auto mb-2 h-6 w-6 opacity-50" />
                      No audit entries yet.
                    </td>
                  </tr>
                ) : (
                  filtered.map((r) => (
                    <tr key={r.id} className="border-b last:border-0 hover:bg-muted/20">
                      <td className="p-3 font-mono text-xs text-muted-foreground">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                      <td className="p-3 font-mono text-xs">{r.action}</td>
                      <td className="p-3 text-xs">
                        <div>{r.target_name || r.target_id || "—"}</div>
                        {r.target_type && (
                          <div className="text-[10px] text-muted-foreground">
                            {r.target_type}
                            {r.target_id ? ` · ${r.target_id}` : ""}
                          </div>
                        )}
                      </td>
                      <td className="p-3 text-xs">
                        <Badge variant="outline">{r.actor || "system"}</Badge>
                      </td>
                      <td className="p-3">
                        <span className="inline-flex items-center gap-1 text-xs capitalize">
                          <OutcomeIcon o={r.outcome} /> {r.outcome}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-muted-foreground">
                        {r.details || "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </DashboardLayout>
  );
}
