import { HealthCenter, DailyReport, CenterDailyStatus } from "./types";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeCSV(val: string | number | null | undefined): string {
  const s = String(val ?? "");
  return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s.replace(/"/g, '""')}"` : s;
}

function arrayToCSV(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const lines = [headers.map(escapeCSV).join(",")];
  rows.forEach((row) => lines.push(row.map(escapeCSV).join(",")));
  return lines.join("\n");
}

// ─── Health Centers Export ───

export function exportHealthCentersCSV(centers: HealthCenter[]) {
  const headers = ["Name", "Province", "District", "Database", "Status", "Last Sync", "Data Size (MB)", "Risk Score", "Success Rate %", "AnyDesk", "RustDesk"];
  const rows = centers.map((c) => [
    c.name, c.province, c.district, c.database_name, c.status,
    new Date(c.last_sync).toLocaleString(), c.data_size_mb.toFixed(1),
    c.risk_score, c.success_rate, c.anydesk_id ?? "", c.rustdesk_id ?? "",
  ]);
  const csv = arrayToCSV(headers, rows);
  downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8;" }), `health_centers_${new Date().toISOString().split("T")[0]}.csv`);
}

export function exportHealthCentersExcel(centers: HealthCenter[]) {
  // Build a simple HTML table that Excel can open
  const headers = ["Name", "Province", "District", "Database", "Status", "Last Sync", "Data Size (MB)", "Risk Score", "Success Rate %", "AnyDesk", "RustDesk"];
  let html = `<html><head><meta charset="utf-8"></head><body><table border="1"><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>`;
  centers.forEach((c) => {
    html += `<tr><td>${c.name}</td><td>${c.province}</td><td>${c.district}</td><td>${c.database_name}</td><td>${c.status}</td><td>${new Date(c.last_sync).toLocaleString()}</td><td>${c.data_size_mb.toFixed(1)}</td><td>${c.risk_score}</td><td>${c.success_rate}</td><td>${c.anydesk_id ?? ""}</td><td>${c.rustdesk_id ?? ""}</td></tr>`;
  });
  html += `</tbody></table></body></html>`;
  downloadBlob(new Blob([html], { type: "application/vnd.ms-excel" }), `health_centers_${new Date().toISOString().split("T")[0]}.xls`);
}

// ─── Reports Export ───

export function exportReportsCSV(reports: DailyReport[]) {
  const headers = ["Date", "Full Sync Centers", "Partial Centers", "No Data Centers", "Volume (GB)", "Rows Synced"];
  const rows = reports.map((r) => [r.date, r.full_sync_centers, r.partial_centers, r.no_data_centers, r.total_data_volume_gb, r.total_rows_synced]);
  downloadBlob(new Blob([arrayToCSV(headers, rows)], { type: "text/csv;charset=utf-8;" }), `reports_daily_${new Date().toISOString().split("T")[0]}.csv`);
}

export function exportReportsExcel(reports: DailyReport[]) {
  const headers = ["Date", "Full Sync", "Partial", "No Data", "Volume (GB)", "Rows Synced"];
  let html = `<html><head><meta charset="utf-8"></head><body><table border="1"><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>`;
  reports.forEach((r) => {
    html += `<tr><td>${r.date}</td><td>${r.full_sync_centers}</td><td>${r.partial_centers}</td><td>${r.no_data_centers}</td><td>${r.total_data_volume_gb}</td><td>${r.total_rows_synced}</td></tr>`;
  });
  html += `</tbody></table></body></html>`;
  downloadBlob(new Blob([html], { type: "application/vnd.ms-excel" }), `reports_daily_${new Date().toISOString().split("T")[0]}.xls`);
}

export function exportReportsPDF(reports: DailyReport[]) {
  // Generate a printable HTML and trigger browser print-to-PDF
  const w = window.open("", "_blank");
  if (!w) return;
  let html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Daily Sync Reports</title><style>body{font-family:Arial,sans-serif;padding:20px}table{width:100%;border-collapse:collapse;margin-top:16px}th,td{border:1px solid #ccc;padding:8px;text-align:left;font-size:13px}th{background:#0d9488;color:#fff}h1{color:#0d9488;font-size:20px}h2{font-size:14px;color:#666;margin-top:4px}</style></head><body>`;
  html += `<h1>Medisoft — Daily Sync Reports</h1><h2>Generated: ${new Date().toLocaleString()}</h2>`;
  html += `<table><thead><tr><th>Date</th><th>Full Sync</th><th>Partial</th><th>No Data</th><th>Volume (GB)</th><th>Rows Synced</th></tr></thead><tbody>`;
  reports.forEach((r) => {
    html += `<tr><td>${r.date}</td><td>${r.full_sync_centers}</td><td>${r.partial_centers}</td><td>${r.no_data_centers}</td><td>${r.total_data_volume_gb}</td><td>${r.total_rows_synced.toLocaleString()}</td></tr>`;
  });
  html += `</tbody></table><script>setTimeout(()=>{window.print();},500)<\/script></body></html>`;
  w.document.write(html);
  w.document.close();
}

export function exportCenterReportCSV(details: CenterDailyStatus[], date: string) {
  const headers = ["Health Center", "Status", "Rows Synced", "Data (MB)", "Last Sync"];
  const rows = details.map((d) => [d.center_name, d.sync_status, d.rows_synced, d.data_volume_mb, d.last_sync_time ? new Date(d.last_sync_time).toLocaleTimeString() : "—"]);
  downloadBlob(new Blob([arrayToCSV(headers, rows)], { type: "text/csv;charset=utf-8;" }), `report_${date}_by_center.csv`);
}

// ─── Operational Reports Export ───

export interface OperationalRow {
  day: string;
  center_id?: string;
  center_name: string;
  foss_id: string;
  head_name: string | null;
  head_phone: string | null;
  last_seen: string | null;
  io_down: boolean;
  sql_down: boolean;
  both_down: boolean;
  outdated: boolean;
  sms_sent: number;
  sms_delivered: number;
  sms_to_head: number;
  sms_to_admin: number;
  head_notified: boolean;
}

const OP_HEADERS = [
  "Day", "Health Center", "FOSS ID", "Head of HC", "Head Phone",
  "Last Seen", "IO Down", "SQL Down", "Both Down", "Outdated",
  "SMS Sent", "SMS Delivered", "SMS → Head", "SMS → Admin", "Head Notified"
];

const opRow = (r: OperationalRow) => [
  r.day, r.center_name, r.foss_id, r.head_name ?? "", r.head_phone ?? "",
  r.last_seen ?? "—",
  r.io_down ? "Yes" : "No",
  r.sql_down ? "Yes" : "No",
  r.both_down ? "Yes" : "No",
  r.outdated ? "Yes" : "No",
  r.sms_sent, r.sms_delivered, r.sms_to_head, r.sms_to_admin,
  r.head_notified ? "Yes" : "No",
];

export function exportOperationalCSV(rows: OperationalRow[]) {
  const csv = arrayToCSV(OP_HEADERS, rows.map(opRow));
  downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8;" }),
    `operational_report_${new Date().toISOString().split("T")[0]}.csv`);
}

export function exportOperationalExcel(rows: OperationalRow[]) {
  let html = `<html><head><meta charset="utf-8"></head><body><table border="1"><thead><tr>${OP_HEADERS.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>`;
  rows.forEach((r) => {
    html += `<tr>${opRow(r).map((c) => `<td>${c}</td>`).join("")}</tr>`;
  });
  html += `</tbody></table></body></html>`;
  downloadBlob(new Blob([html], { type: "application/vnd.ms-excel" }),
    `operational_report_${new Date().toISOString().split("T")[0]}.xls`);
}
