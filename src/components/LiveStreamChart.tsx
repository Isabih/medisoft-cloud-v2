import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity, Zap } from "lucide-react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Tick {
  t: string;          // HH:MM:SS
  rows: number;
  bytes: number;
  centers: number;
}

const WINDOW = 60; // 60-second rolling window

/**
 * Live throughput chart driven by the same WS connection used elsewhere.
 * Subscribes to `data_ingest` events on the global WS bus; degrades to
 * simulated zero-bars when WS is silent so the chart isn't blank.
 */
export function LiveStreamChart() {
  const [ticks, setTicks] = useState<Tick[]>(() => {
    const now = Date.now();
    return Array.from({ length: WINDOW }, (_, i) => {
      const d = new Date(now - (WINDOW - i - 1) * 1000);
      return { t: d.toLocaleTimeString(), rows: 0, bytes: 0, centers: 0 };
    });
  });
  const accumRef = useRef<{ rows: number; bytes: number; centers: Set<string> }>({
    rows: 0,
    bytes: 0,
    centers: new Set(),
  });

  // Listen on a custom event the WebSocket hook will dispatch.
  useEffect(() => {
    const onIngest = (e: Event) => {
      const detail = (e as CustomEvent).detail || {};
      accumRef.current.rows += Number(detail.rows || 0);
      accumRef.current.bytes += Number(detail.bytes || 0);
      if (detail.center_id) accumRef.current.centers.add(String(detail.center_id));
    };
    window.addEventListener("medisoft:data_ingest", onIngest);
    return () => window.removeEventListener("medisoft:data_ingest", onIngest);
  }, []);

  // Per-second tick.
  useEffect(() => {
    const id = setInterval(() => {
      const a = accumRef.current;
      const tick: Tick = {
        t: new Date().toLocaleTimeString(),
        rows: a.rows,
        bytes: Math.round(a.bytes / 1024), // KB
        centers: a.centers.size,
      };
      accumRef.current = { rows: 0, bytes: 0, centers: new Set() };
      setTicks((prev) => [...prev.slice(-WINDOW + 1), tick]);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const latest = ticks[ticks.length - 1];
  const peak = Math.max(...ticks.map((t) => t.rows));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            Live Data Stream (rows/sec)
          </span>
          <span className="flex items-center gap-3 text-xs font-normal text-muted-foreground">
            <span>
              Now: <b className="text-success">{latest?.rows ?? 0}</b>
            </span>
            <span>
              Peak (60s): <b>{peak}</b>
            </span>
            <span>
              Active centers: <b>{latest?.centers ?? 0}</b>
            </span>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="h-44 pt-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={ticks} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="liveStream" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.6} />
                <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="t" tick={false} stroke="hsl(var(--border))" />
            <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--border))" allowDecimals={false} />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 8,
                fontSize: 11,
              }}
            />
            <Area
              type="monotone"
              dataKey="rows"
              stroke="hsl(var(--primary))"
              strokeWidth={1.5}
              fill="url(#liveStream)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
