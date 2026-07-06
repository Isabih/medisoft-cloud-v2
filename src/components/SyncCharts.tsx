import { useQuery } from "@tanstack/react-query";
import { fetchSyncActivity } from "@/lib/api";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Loader2 } from "lucide-react";

interface SyncActivityItem {
  hour: string;
  syncs: number;
  failed: number;
}

interface DataVolumeItem {
  hour: string;
  volume_mb: number;
}

interface RiskItem {
  name: string;
  risk: number;
}

export function SyncCharts() {
  const { data, isLoading } = useQuery<{
    sync_activity: SyncActivityItem[];
    data_volume: DataVolumeItem[];
    risk_scores: RiskItem[];
  }>({
    queryKey: ["sync-activity"],
    queryFn: async () => (await fetchSyncActivity()).data,
    refetchInterval: 60000,
  });

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {[1, 2, 3].map(i => (
          <div key={i} className="bg-card rounded-xl border p-5 shadow-sm flex items-center justify-center h-[260px]">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ))}
      </div>
    );
  }

  const { sync_activity = [], data_volume = [], risk_scores = [] } = data;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Sync Activity */}
      <div className="bg-card rounded-xl border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-card-foreground mb-4">Sync Activity (24h)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={sync_activity}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(200 15% 88%)" />
            <XAxis dataKey="hour" tick={{ fontSize: 10 }} interval={5} stroke="hsl(200 10% 45%)" />
            <YAxis tick={{ fontSize: 10 }} stroke="hsl(200 10% 45%)" />
            <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            <Area type="monotone" dataKey="syncs" stroke="hsl(180 70% 40%)" fill="hsl(180 70% 40% / 0.2)" strokeWidth={2} />
            <Area type="monotone" dataKey="failed" stroke="hsl(0 72% 51%)" fill="hsl(0 72% 51% / 0.15)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Data Volume */}
      <div className="bg-card rounded-xl border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-card-foreground mb-4">Data Volume/Hour (MB)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data_volume}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(200 15% 88%)" />
            <XAxis dataKey="hour" tick={{ fontSize: 10 }} interval={5} stroke="hsl(200 10% 45%)" />
            <YAxis tick={{ fontSize: 10 }} stroke="hsl(200 10% 45%)" />
            <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            <Bar dataKey="volume_mb" fill="hsl(180 70% 40%)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Risk Score */}
      <div className="bg-card rounded-xl border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-card-foreground mb-4">Risk Score by Center</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={risk_scores} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(200 15% 88%)" />
            <XAxis type="number" tick={{ fontSize: 10 }} stroke="hsl(200 10% 45%)" />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 9 }} width={70} stroke="hsl(200 10% 45%)" />
            <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            <Bar dataKey="risk" radius={[0, 4, 4, 0]} fill="hsl(180 70% 40%)">
              {risk_scores.map((entry, i) => (
                <rect key={i} fill={entry.risk >= 60 ? "hsl(0 72% 51%)" : entry.risk >= 30 ? "hsl(38 92% 50%)" : "hsl(142 71% 45%)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
