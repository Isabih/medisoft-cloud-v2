import { HealthCenter } from "@/lib/types";

export const MONITORING_SELECTED_CENTER_KEY = "monitoring_selected_center_id";

export const normalizeText = (value?: string | null) =>
  (value || "").trim().toLowerCase();

export const matchesHealthCenterQuery = (
  center: Partial<HealthCenter> & Record<string, any>,
  query: string
) => {
  const q = normalizeText(query);
  if (!q) return true;

  const haystacks = [
    center.name,
    center.database_name,
    center.foss_id,
    center.province,
    center.district,
    center.anydesk_id,
    center.rustdesk_id,
    center.phone_number_1,
    center.phone_number_2,
  ];

  return haystacks.some((value) => normalizeText(String(value || "")).includes(q));
};

export const rememberSelectedHealthCenter = (centerId: string) => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MONITORING_SELECTED_CENTER_KEY, centerId);
};

export const readRememberedHealthCenter = () => {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(MONITORING_SELECTED_CENTER_KEY) || "";
};

export const clearRememberedHealthCenter = () => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(MONITORING_SELECTED_CENTER_KEY);
};

export const findHealthCenterByDatabaseName = <T extends { database_name?: string | null }>(
  rows: T[],
  databaseName?: string | null
) => {
  const target = normalizeText(databaseName);
  if (!target) return undefined;
  return rows.find((row) => normalizeText(row.database_name) === target);
};
