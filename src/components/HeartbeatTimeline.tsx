import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceDot,
} from "recharts";
import { Activity, MessageSquare, Loader2, Info, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip as UiTooltip,
  TooltipContent as UiTooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { fetchHeartbeatTimeline } from "@/lib/api";
import { LIVE_QUERY_OPTIONS } from "@/lib/query";

type Bucket = {
  bucket: string;
  total: number;
  success: number;
  partial: number;
  failure: number;
  avg_cpu: number | null;
  avg_ram: number | null;
};

type SmsMarker = {
  id: string | number;
  sent_at: string;
  status: string;
  recipient_role: string | null;
  to_number: string;
  message: string;
};

const hourLabel = (s: string) => {
  const d = new Date(s.replace(" ", "T"));
  return isNaN(d.getTime()) ? s.slice(-8, -3) : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

// Okabe-Ito colour-blind safe palette
const CB_COLORS = {
  success: "#009E73", // bluish green
  partial: "#E69F00", // orange
  failure: "#D55E00", // vermillion
  sms: "#0072B2",     // blue
};

const LegendChip = ({
  color,
  label,
  hint,
  Icon,
}: {
  color: string; // bg-class for the swatch
  label: string;
  hint: string;
  Icon: any;
}) => (
  <TooltipProvider delayDuration={150}>
    <UiTooltip>
      <TooltipTrigger asChild>
        <span
          role="button"
          tabIndex={0}
          aria-label={`${label}: ${hint}`}
          className="inline-flex cursor-help items-center gap-1.5 rounded-full border bg-card/50 px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              (e.currentTarget as HTMLElement).focus();
            }
          }}
        >
          <span className={`inline-block h-2.5 w-2.5 rounded-sm ${color}`} aria-hidden="true" />
          <Icon className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
          {label}
        </span>
      </TooltipTrigger>
      <UiTooltipContent className="max-w-[260px] text-xs">{hint}</UiTooltipContent>
    </UiTooltip>
  </TooltipProvider>
);

const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload as any;
  const total = (d?.success || 0) + (d?.partial || 0) + (d?.failure || 0);
  return (
    <div className="rounded-lg border bg-card p-2 text-[11px] shadow-md">
      <div className="mb-1 font-semibold">{label}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        <span className="text-success">● Healthy</span><span className="font-mono">{d?.success ?? 0}</span>
        <span className="text-warning">● Partial</span><span className="font-mono">{d?.partial ?? 0}</span>
        <span className="text-destructive">● Failure</span><span className="font-mono">{d?.failure ?? 0}</span>
        <span className="text-muted-foreground">Total beats</span><span className="font-mono">{total}</span>
        {d?.smsCount > 0 && (
          <>
            <span className="text-primary">◆ SMS sent</span>
            <span className="font-mono">{d.smsCount}</span>
          </>
        )}
      </div>
    </div>
  );
};

export function HeartbeatTimeline({ centerId, hours = 24 }: { centerId: string; hours?: number }) {
  const { data, isPending, isFetching } = useQuery({
    queryKey: ["heartbeat-timeline", centerId, hours],
    queryFn: async () => (await fetchHeartbeatTimeline(centerId, hours)).data,
    enabled: !!centerId,
    refetchInterval: 60_000,
    ...LIVE_QUERY_OPTIONS,
  });

  const buckets: Bucket[] = data?.buckets || [];
  const sms: SmsMarker[] = data?.sms_markers || [];

  const smsByBucket = new Map<string, SmsMarker[]>();
  sms.forEach((m) => {
    const d = new Date(m.sent_at);
    if (isNaN(d.getTime())) return;
    d.setMinutes(0, 0, 0);
    const key = d.toISOString().slice(0, 13);
    const arr = smsByBucket.get(key) || [];
    arr.push(m);
    smsByBucket.set(key, arr);
  });

  const chartData = buckets.map((b) => {
    const key = new Date(b.bucket.replace(" ", "T")).toISOString().slice(0, 13);
    return {
      ...b,
      label: hourLabel(b.bucket),
      smsCount: smsByBucket.get(key)?.length || 0,
    };
  });

  const totalSms = sms.length;
  const deliveredSms = sms.filter((s) => s.status === "sent" || s.status === "delivered").length;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            Last {hours}h heartbeat &amp; sync health
            {isFetching && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
            <span className="ml-1 inline-flex items-center gap-1 text-[10px] font-normal text-muted-foreground">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
              live
            </span>
          </span>
          <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
            <Badge variant="outline" className="gap-1">
              <MessageSquare className="h-3 w-3" /> {deliveredSms}/{totalSms} SMS
            </Badge>
          </span>
        </CardTitle>
        <div className="mt-2 flex flex-wrap items-center gap-2" role="list" aria-label="Status legend">
          <LegendChip
            color="bg-[#009E73]"
            Icon={CheckCircle2}
            label="Healthy"
            hint="Heartbeat received this hour with replication IO+SQL both running (Yes/On). Colour-blind safe: bluish green (Okabe-Ito)."
          />
          <LegendChip
            color="bg-[#E69F00]"
            Icon={AlertTriangle}
            label="Partial"
            hint="Heartbeat received but one replication thread (IO or SQL) was not running, or sync lagged. Colour-blind safe: orange (Okabe-Ito)."
          />
          <LegendChip
            color="bg-[#D55E00]"
            Icon={XCircle}
            label="Failure"
            hint="Heartbeat missed or both IO and SQL replication threads were down this hour. Colour-blind safe: vermillion (Okabe-Ito)."
          />
          <LegendChip
            color="bg-[#0072B2]"
            Icon={MessageSquare}
            label="SMS alert"
            hint="Blue dot above a bar marks an hour in which an SMS alert was triggered (head of HC or admin). Counted in the badge on the right."
          />
          <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-muted-foreground">
            <Info className="h-3 w-3" aria-hidden="true" /> Tab to focus, hover bars for hourly counts
          </span>
        </div>
      </CardHeader>
      <CardContent
        className="h-56 pt-0"
        role="img"
        aria-label={`Heartbeat and sync health for the last ${hours} hours. Healthy ${chartData.reduce((s, d) => s + (d.success || 0), 0)}, partial ${chartData.reduce((s, d) => s + (d.partial || 0), 0)}, failure ${chartData.reduce((s, d) => s + (d.failure || 0), 0)}, ${totalSms} SMS alerts.`}
      >
        {isPending && chartData.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading timeline…
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            No heartbeats received in the last {hours}h.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="hsl(var(--border))" />
              <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--border))" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="success" stackId="a" name="Healthy" fill={CB_COLORS.success} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="partial" stackId="a" name="Partial" fill={CB_COLORS.partial} isAnimationActive={false} />
              <Bar dataKey="failure" stackId="a" name="Failure" fill={CB_COLORS.failure} isAnimationActive={false} />
              {chartData
                .filter((d) => d.smsCount > 0)
                .map((d, idx) => (
                  <ReferenceDot
                    key={idx}
                    x={d.label}
                    y={(d.success || 0) + (d.partial || 0) + (d.failure || 0) + 0.5}
                    r={5}
                    fill={CB_COLORS.sms}
                    stroke="hsl(var(--card))"
                    strokeWidth={2}
                  />
                ))}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
