import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { CenterMapPoint } from "@/lib/types";

// Fix default marker icons for bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const STATUS_COLORS: Record<string, string> = {
  healthy: "#16a34a",
  warning: "#eab308",
  critical: "#dc2626",
  offline: "#1f2937",
};

// Rwanda bounding box roughly
const RWANDA_CENTER: [number, number] = [-1.9403, 29.8739];

interface Props {
  points: CenterMapPoint[];
  height?: number;
}

export function RwandaMap({ points, height = 480 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  const validPoints = useMemo(
    () => points.filter((p) => Number.isFinite(Number(p.latitude)) && Number.isFinite(Number(p.longitude))),
    [points]
  );

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: RWANDA_CENTER,
      zoom: 8,
      scrollWheelZoom: true,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
  }, []);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();

    validPoints.forEach((p) => {
      const color = STATUS_COLORS[p.health_status] || "#64748b";
      const marker = L.circleMarker([Number(p.latitude), Number(p.longitude)], {
        radius: 9,
        fillColor: color,
        color: "#0f172a",
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.9,
      }).bindPopup(
        `<div style="font-family:ui-sans-serif,system-ui;font-size:12px;min-width:180px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">${escapeHtml(p.name)}</div>
          <div style="color:#64748b">${escapeHtml(p.district || "")}, ${escapeHtml(p.province || "")}</div>
          <div style="margin-top:6px">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>
            Health <b>${p.health_score}</b>/100 · ${p.health_status.toUpperCase()}
          </div>
          <div style="margin-top:4px;color:#475569">
            IO: ${p.io_running || "?"} · SQL: ${p.sql_running || "?"} · lag: ${p.seconds_behind ?? "?"}s
          </div>
        </div>`
      );
      marker.addTo(layer);
    });

    if (validPoints.length > 0 && mapRef.current) {
      const bounds = L.latLngBounds(
        validPoints.map((p) => [Number(p.latitude), Number(p.longitude)] as [number, number])
      );
      mapRef.current.fitBounds(bounds.pad(0.25), { maxZoom: 11 });
    }
  }, [validPoints]);

  return (
    <div className="relative overflow-hidden rounded-2xl border">
      <div ref={containerRef} style={{ height }} className="z-0" />
      <div className="pointer-events-none absolute bottom-3 left-3 z-[400] flex gap-2 rounded-lg bg-white/90 px-3 py-2 text-xs shadow">
        {Object.entries(STATUS_COLORS).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1 capitalize">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: v }} />
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}

function escapeHtml(s: string): string {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c] as string));
}
