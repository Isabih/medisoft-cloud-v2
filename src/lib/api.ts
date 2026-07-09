import axios from "axios";
import type { RegisterHealthCenterPayload, UnregisteredDatabase } from "@/lib/types";

/*
------------------------------------------------------------
API BASE URL
------------------------------------------------------------
Priority:
1. localStorage override (Settings → API base URL)
2. Vite env var VITE_API_BASE_URL (build-time)
3. Same-origin "/api/v1" — works when the frontend is served by
   the same host/nginx that proxies the FastAPI backend.
*/

function resolveApiBaseUrl(): string {
  const override = typeof window !== "undefined" ? localStorage.getItem("api_base_url") : null;
  if (override && override.trim()) return override.trim().replace(/\/$/, "");

  const envBase = (import.meta as any).env?.VITE_API_BASE_URL as string | undefined;
  if (envBase && envBase.trim()) return envBase.trim().replace(/\/$/, "");

  if (typeof window !== "undefined") {
    return `${window.location.origin}/api/v1`;
  }
  return "/api/v1";
}

export const API_BASE_URL = resolveApiBaseUrl();

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

/*
------------------------------------------------------------
AUTH TOKEN INTERCEPTOR
------------------------------------------------------------
Automatically attach Bearer token if present
*/
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

/*
============================================================
AUTH
============================================================
*/

export const loginUser = (username: string, password: string) =>
  api.post("/auth/login", { username, password });

export const forgotPassword = (identifier: string) =>
  api.post("/auth/forgot-password", { identifier });

/*
============================================================
HEALTH CENTERS
============================================================
*/

export const fetchHealthCenters = () =>
  api.get("/health-centers");

export const fetchHealthCenter = (id: string) =>
  api.get(`/health-centers/${id}`);

export const registerHealthCenter = (data: RegisterHealthCenterPayload) =>
  api.post("/health-centers", data);

export const validateDatabase = (dbName: string) =>
  api.post("/health-centers/validate-db", {
    database_name: dbName,
  });

/*
============================================================
HEALTH CENTER DETAIL HISTORY
============================================================
*/

export const fetchReplicationHistory = (centerId: string) =>
  api.get(`/health-centers/${centerId}/replication-history`);

export const fetchBackupHistory = (centerId: string) =>
  api.get(`/health-centers/${centerId}/backup-history`);

export const fetchMetricsHistory = (centerId: string) =>
  api.get(`/health-centers/${centerId}/metrics-history`);

export const fetchCenterTimeline = (centerId: string) =>
  api.get(`/health-centers/${centerId}/timeline`);

/*
============================================================
MONITORED DATABASES
============================================================
*/

export const fetchMonitoredDatabases = () =>
  api.get("/monitored-databases");

export const fetchMonitoredDatabase = (id: string) =>
  api.get(`/monitored-databases/${id}`);

/*
============================================================
DRIFT DETECTION
============================================================
*/

export const fetchDriftReports = () =>
  api.get("/drift/reports");

export const fetchDriftReport = (centerId: string) =>
  api.get(`/drift/reports/${centerId}`);

/*
============================================================
DASHBOARD
============================================================
*/

export const fetchCentersLive = () =>
  api.get("/dashboard/centers-live");

export const fetchDashboardKPIs = () =>
  api.get("/dashboard/kpis");

export const fetchDashboardSummary = () =>
  api.get("/dashboard/summary");

export const fetchSyncActivity = () =>
  api.get("/dashboard/sync-activity");

export const fetchAlerts = () =>
  api.get("/dashboard/alerts");

export const fetchUnregisteredDbs = () =>
  api.get("/dashboard/unregistered-dbs");

/*
============================================================
OPERATIONS CENTER + TIMELINE + AGENT VERSION
============================================================
*/

export const fetchOperationsSummary = () => api.get("/operations/summary");
export const fetchOperationsMap = () => api.get("/operations/map");
export const fetchCenterTimelineAggregated = (centerId: string) =>
  api.get(`/timeline/${centerId}`);
export const postTimelineEvent = (payload: {
  center_id: string;
  event_type: string;
  title: string;
  severity?: string;
  message?: string;
  center_name?: string;
}) => api.post("/timeline", payload);
export const fetchLatestAgentVersion = () => api.get("/agent-version/latest");
export const fetchDatabaseIntegritySummary = () => api.get("/database-integrity/summary");
export const fetchDatabaseIntegrityByCenter = (centerId: string) => api.get(`/database-integrity/centers/${centerId}`);

/*
============================================================
ALERTS
============================================================
*/

export const fetchActiveAlerts = () =>
  api.get("/alerts/active");

export const fetchAlertsByCenter = (centerId: string) =>
  api.get("/alerts", {
    params: { center_id: centerId },
  });

export const resolveAlert = (alertId: string) =>
  api.post(`/alerts/${alertId}/resolve`);

/*
============================================================
DATABASE DISCOVERY
============================================================
*/

export const fetchAvailableDatabases = () =>
  api.get<UnregisteredDatabase[]>("/databases/available");

/*
============================================================
HEARTBEAT
============================================================
*/

export const sendHeartbeat = (data: {
  foss_id: string;
  mysql_status: string;
  internet_status: string;
  cloud_connection: string;
  cpu_usage: number;
  ram_usage: number;
  disk_usage: number;
  sent_at: string;
}) => api.post("/heartbeat", data);

/*
============================================================
REPLICATION REPORT
============================================================
*/

export const sendReplicationReport = (data: {
  foss_id: string;
  io_running: string;
  sql_running: string;
  seconds_behind: number | null;
  last_io_error: string;
  last_sql_error: string;
  checked_at: string;
}) => api.post("/replication/report", data);

/*
============================================================
DATABASE METRICS
============================================================
*/

export const sendDatabaseMetrics = (data: {
  foss_id: string;
  top_tables: {
    name: string;
    rows: number;
    size_mb: number;
  }[];
  total_size_mb: number;
}) => api.post("/metrics/database", data);

/*
============================================================
BACKUP REPORT
============================================================
*/

export const sendBackupReport = (data: {
  foss_id: string;
  backup_date: string;
  status: string;
  file_size_mb: number;
  duration_seconds: number;
}) => api.post("/backup/report", data);

/*
============================================================
BACKUPS
============================================================
*/

export const fetchBackups = (params?: {
  center_id?: string;
  from?: string;
  to?: string;
}) =>
  api.get("/backups", { params });

export const fetchBackupsByCenter = (centerId: string) =>
  api.get(`/backups/center/${centerId}`);

/*
============================================================
REPORTS
============================================================
*/

export const fetchDailyReports = (params?: {
  from?: string;
  to?: string;
}) =>
  api.get("/reports/daily", { params });

export const fetchOperationalReport = (params?: { from?: string; to?: string }) =>
  api.get("/reports/operational", { params });

export const fetchHeartbeatTimeline = (centerId: string, hours = 24) =>
  api.get(`/health-centers/${centerId}/heartbeat-timeline`, { params: { hours } });

export const fetchCenterReport = (
  centerId: string,
  params?: { from?: string; to?: string }
) =>
  api.get(`/reports/center/${centerId}`, { params });

export const downloadReport = (date: string, format: "pdf" | "excel") =>
  api.get(`/reports/download/${date}`, {
    params: { format },
    responseType: "blob",
  });

export const fetchCloudStatus = () =>
  api.get("/cloud/status");

/*
============================================================
SETTINGS
============================================================
*/


/*
============================================================
RETENTION + INCIDENT HISTORY
============================================================
*/
export const fetchRetentionStatus = () => api.get("/retention/status");
export const runRetentionCleanup = () => api.post("/retention/run", null, { params: { force: true } });
export const fetchIncidentHistory = (params?: { from?: string; to?: string; foss_id?: string; event_type?: string; limit?: number }) =>
  api.get("/reports/incident-history", { params });

export const fetchSettings = () =>
  api.get("/settings");

export const updateSettings = (data: any) =>
  api.put("/settings", data);

export const sendTestSms = (to: string) =>
  api.post("/settings/sms/test", { to });

export const sendTestEmail = (to: string) =>
  api.post("/settings/email/test", { to });

/*
============================================================
SYNC STATUS
============================================================
*/

export const fetchSyncStatus = () =>
  api.get("/sync/status");

/*
============================================================
HEALTH CHECK
============================================================
*/

export const healthCheck = () =>
  api.get("/health");

/*
============================================================
AUTO-HEAL (Replication Guardian)
============================================================
*/
export const autoHealChannel = (channelName: string) =>
  api.post(`/replication-guardian/repair/${encodeURIComponent(channelName)}`);

/*
============================================================
AI DIAGNOSE (Lovable AI Gateway proxy)
============================================================
*/
export const aiDiagnose = (centerId: string, context?: Record<string, unknown>) =>
  api.post("/ai/diagnose", { center_id: centerId, context: context || {} });

/*
============================================================
SMS LOGS
============================================================
*/
export const fetchSmsLogs = async (params?: { from?: string; to?: string; center_id?: string }) => {
  const res = await api.get("/sms/logs", { params });
  const data = res.data;
  return {
    ...res,
    data: Array.isArray(data) ? data : (data?.logs || []),
  };
};

export const resendSms = (id: string) => api.post(`/sms/${id}/resend`);

/*
============================================================
AUDIT LOGS
============================================================
*/
export const fetchAuditLogs = (params?: {
  target_type?: string;
  target_id?: string;
  action?: string;
  outcome?: string;
  limit?: number;
}) => api.get("/audit/logs", { params });

export const writeAuditLog = (payload: {
  action: string;
  target_type?: string;
  target_id?: string;
  target_name?: string;
  outcome?: "success" | "failure" | "pending";
  details?: string;
  actor?: string;
}) => api.post("/audit/log", payload);

/*
============================================================
AGENT REMOTE ACTIONS
============================================================
*/
export const triggerAgentAction = (
  fossId: string,
  action: "restart-mysql" | "restart-replica" | "reset-replica" | "start-replica" | "stop-replica",
  requestedBy = "admin",
) => api.post(`/agent/${fossId}/${action}`, { requested_by: requestedBy });

/*
============================================================
SYSTEM HEALTH CHECK (post-install verification)
============================================================
*/
export const fetchSystemHealthCheck = () => api.get("/system/health-check");

export default api;