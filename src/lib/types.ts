export interface CenterLive {
  center_id: string;
  name: string;
  province: string;
  district: string;
  database_name: string;
  foss_id: string;
  status: "online" | "offline" | "partial";
  internet_status: "online" | "offline";
  mysql_status: "online" | "offline";
  cloud_connection: "ok" | "failed";
  last_seen: string;
  replica_io: string;
  replica_sql: string;
  seconds_behind: number | null;
  last_backup: string | null;
  backup_status: "success" | "failed" | null;
  cpu_usage: number;
  ram_usage: number;
  disk_usage: number;
  drift_detected: boolean;
  data_health_score?: number | null;
  integrity_status?: string | null;
  local_rows_count?: number | null;
  cloud_rows_count?: number | null;
  rows_difference?: number | null;
  local_size_mb?: number | null;
  cloud_size_mb?: number | null;
  size_difference_mb?: number | null;
  local_table_count?: number | null;
  cloud_table_count?: number | null;
  latest_local_time?: string | null;
  latest_cloud_time?: string | null;
  integrity_summary?: string | null;
  risk_score: number;
  unresolved_alerts: number;
  latitude?: number | null;
  longitude?: number | null;
  agent_version?: string | null;
  health_score?: number | null;
  phone_number_1?: string | null;
  phone_contact_1?: string | null;
  phone_role_1?: string | null;
  phone_number_2?: string | null;
  phone_contact_2?: string | null;
  phone_role_2?: string | null;
  anydesk_id?: string | null;
  rustdesk_id?: string | null;
}

export interface OperationsSummary {
  total_centers: number;
  online: number;
  offline: number;
  sql_running: number;
  sql_failed: number;
  io_running: number;
  io_failed: number;
  alerts_today: number;
  critical_open: number;
  databases_monitored: number;
  avg_replication_lag_seconds: number;
}

export interface CenterMapPoint {
  id: string;
  name: string;
  province?: string;
  district?: string;
  latitude: number | null;
  longitude: number | null;
  status?: string;
  health_score: number;
  health_status: "healthy" | "warning" | "critical" | "offline";
  cpu_usage?: number;
  ram_usage?: number;
  disk_usage?: number;
  seconds_behind?: number | null;
  io_running?: string | null;
  sql_running?: string | null;
}

export interface TimelineFeedItem {
  id: string | number;
  event_type: string;
  severity: "info" | "warning" | "critical" | "success";
  title: string;
  message?: string | null;
  created_at: string;
}
export interface CloudStatus {
  server_name: string;
  server_status: "online" | "offline" | "warning";
  api_status: string;
  database_status: string;
  internet_status: string;
  cpu_usage: number;
  cpu_cores: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_free_gb: number;
  disk_used_gb: number;
  disk_total_gb: number;
  disk_free_gb: number;
  disk_percent: number;
  uptime: string;
  load_average: string;
  last_updated: string;
}

export interface DashboardKPIs {
  total_centers: number;
  online: number;
  partial: number;
  offline: number;
  critical_alerts: number;
  warning_alerts: number;
  missing_backups: number;
  high_lag_centers: number;
  high_ram_centers: number;
  high_disk_centers: number;
  high_drift_databases?: number;
}

export interface HealthCenter {
  id: string;
  name: string;
  province: string;
  district: string;
  database_name: string;
  foss_id: string;
  registered_date: string;
  expected_sync_interval: number;
  last_seen: string;
  last_sync: string;
  last_failed_sync: string | null;
  status: "online" | "offline" | "partial";
  internet_status: "online" | "offline";
  mysql_status: "online" | "offline";
  cloud_connection: "ok" | "failed";
  data_size_mb: number;
  risk_score: number;
  success_rate: number;
  avg_rows_per_sync: number;
  avg_data_size_mb: number;
  anydesk_id?: string;
  rustdesk_id?: string;
  phone_number_1?: string;
  phone_contact_1?: string;
  phone_number_2?: string;
  phone_contact_2?: string;
  has_real_foss_id: boolean;
  orders_today?: number;
  last_backup?: BackupRecord | null;
  replication?: ReplicationStatus;
  cpu_usage?: number;
  ram_usage?: number;
  disk_usage?: number;
  drift_detected?: boolean;
  rows_count?: number;
  replication_channel?: string;
}

export interface SmsLog {
  id: string;
  to_number: string;
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

export interface AIDiagnosis {
  root_cause: string;
  fix_steps: string[];
  severity: "info" | "warning" | "critical";
  auto_healable: boolean;
}


export interface ReplicationStatus {
  io_running: string;
  sql_running: string;
  seconds_behind: number | null;
  last_io_error: string;
  last_sql_error: string;
  checked_at: string;
}

export interface MonitoredDatabase {
  id: string;
  health_center_id: string;
  health_center_name: string;
  database_name: string;
  replica_status: "ok" | "offline" | "partial";
  rows_count: number;
  data_size_mb: number;
  last_checked: string | null;
  last_backup: string | null;
  drift_detected: boolean;
  backup_status?: "success" | "failed" | null;
}

export interface DriftReport {
  center_id: string;
  center_name: string;
  database_name: string;
  missing_columns: string[];
  extra_columns: string[];
  missing_rows: number;
  incorrect_fosaid: boolean;
  offline_count: number;
  last_checked: string;
}

export interface BackupRecord {
  id: string;
  center_id: string;
  center_name: string;
  date: string;
  time: string;
  file_name: string;
  file_size_mb: number;
  duration_seconds?: number;
  status: "success" | "failed";
}

export interface HeartbeatPayload {
  foss_id: string;
  mysql_status: "online" | "offline";
  internet_status: "online" | "offline";
  cloud_connection: "ok" | "failed";
  cpu_usage: number;
  ram_usage: number;
  disk_usage: number;
  sent_at: string;
}

export interface ReplicationPayload {
  foss_id: string;
  io_running: string;
  sql_running: string;
  seconds_behind: number | null;
  last_io_error: string;
  last_sql_error: string;
  checked_at: string;
}

export interface DatabaseMetrics {
  foss_id: string;
  top_tables: TableActivity[];
  total_size_mb: number;
}

export interface SyncEvent {
  timestamp: string;
  status: "success" | "failed" | "partial";
  rows_synced: number;
  data_size_mb: number;
  center_id: string;
}

export interface TableActivity {
  table_name: string;
  rows_today: number;
  data_size_mb: number;
  last_sync?: string;
}

export interface Alert {
  id: string;
  center_name: string;
  center_id: string;
  type: "no_sync" | "partial_sync" | "data_drop" | "backup_missing" | "replication_stopped" | "high_lag" | "drift_detected" | "heartbeat_missing" | "high_disk" | "high_ram" | "high_cpu";
  message: string;
  severity: "warning" | "critical";
  timestamp: string;
  resolved_at?: string | null;
}

export interface DailyReport {
  date: string;
  full_sync_centers: number;
  partial_centers: number;
  no_data_centers: number;
  total_data_volume_gb: number;
  total_rows_synced: number;
  center_details?: CenterDailyStatus[];
}

export interface CenterDailyStatus {
  center_id: string;
  center_name: string;
  sync_status: "full" | "partial" | "none";
  rows_synced: number;
  data_volume_mb: number;
  last_sync_time: string | null;
}

export interface UnregisteredDatabase {
  schema_name: string;
  health_center_name?: string;
  province?: string;
  district?: string;
  foss_id?: string;
  replication_channel?: string;
  source_host?: string;
  source_port?: number;
  io_thread?: string;
  sql_thread?: string;
  match_score?: number;
  match_type?: string;
  match_reason?: string;
}
export interface RegisterHealthCenterPayload {
  name: string;
  province: string;
  district: string;
  database_name: string;
  foss_id: string;
  replication_channel: string;
  source_host: string;
  source_port: number;
  expected_sync_interval: number;
  anydesk_id: string;
  rustdesk_id: string;
  phone_number_1: string;
  phone_contact_1: string;
  phone_role_1?: string;
  phone_number_2: string;
  phone_contact_2: string;
  phone_role_2?: string;
  latitude?: number | null;
  longitude?: number | null;
  selected_database_schema?: string;
  selected_database_details?: Partial<UnregisteredDatabase>;
}

export interface TimelineEvent {
  id: string;
  type: string;
  message: string;
  timestamp: string;
  severity?: "info" | "warning" | "critical";
}

export type Province = "Eastern" | "Kigali City" | "Northern" | "Southern" | "Western";

export const PROVINCES_DISTRICTS: Record<Province, string[]> = {
  "Eastern": ["Bugesera", "Gatsibo", "Kayonza", "Kirehe", "Ngoma", "Nyagatare", "Rwamagana"],
  "Kigali City": ["Gasabo", "Kicukiro", "Nyarugenge"],
  "Northern": ["Burera", "Gakenke", "Gicumbi", "Musanze", "Rulindo"],
  "Southern": ["Gisagara", "Huye", "Kamonyi", "Muhanga", "Nyamagabe", "Nyanza", "Nyaruguru", "Ruhango"],
  "Western": ["Karongi", "Ngororero", "Nyabihu", "Nyamasheke", "Rubavu", "Rusizi", "Rutsiro"],
};
