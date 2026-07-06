import { useEffect, useRef, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

export interface WebSocketEvent {
  type:
    | "center_update"
    | "alert_created"
    | "heartbeat"
    | "replication"
    | "backup"
    | "alert"
    | "metrics"
    | "status_change"
    | "data_ingest"
    | "sms_sent"
    | "sms_status"
    | "ai_diagnosis_ready"
    | "source_report";
  center_id?: string;
  payload?: any;
  data?: any;
  timestamp: string;
  rows?: number;
  bytes?: number;
}

interface UseWebSocketOptions {
  fallbackPolling?: boolean;
  pollingInterval?: number;
}

function defaultApiBaseUrl(): string {
  const envBase = (import.meta as any).env?.VITE_API_BASE_URL as string | undefined;
  if (envBase && envBase.trim()) return envBase.trim().replace(/\/$/, "");
  if (typeof window !== "undefined") return `${window.location.origin}/api/v1`;
  return "/api/v1";
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { fallbackPolling = true, pollingInterval = 30000 } = options;
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);
  const [usingPolling, setUsingPolling] = useState(false);
  const attemptRef = useRef(0);
  const maxReconnectAttempts = 5;
  // Stable refs so the connect effect never re-runs on every render
  const handleMessageRef = useRef<(e: MessageEvent) => void>(() => {});
  const connectRef = useRef<() => void>(() => {});

  const getApiBaseUrl = useCallback(() => {
    return localStorage.getItem("api_base_url") || defaultApiBaseUrl();
  }, []);

  const getWsUrl = useCallback(() => {
    const baseUrl = getApiBaseUrl();
    const wsBase = baseUrl
      .replace(/^https:\/\//, "wss://")
      .replace(/^http:\/\//, "ws://")
      .replace(/\/api\/v1$/, "");

    return `${wsBase}/ws/monitor`;
  }, [getApiBaseUrl]);

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["centers-live"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
    queryClient.invalidateQueries({ queryKey: ["alerts-active"] });
    queryClient.invalidateQueries({ queryKey: ["health-centers"] });
    queryClient.invalidateQueries({ queryKey: ["monitored-databases"] });
  }, [queryClient]);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const wsEvent: WebSocketEvent = JSON.parse(event.data);

        switch (wsEvent.type) {
          case "center_update":
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
            queryClient.invalidateQueries({ queryKey: ["monitored-databases"] });

            if (wsEvent.center_id) {
              queryClient.invalidateQueries({
                queryKey: ["health-center", wsEvent.center_id],
              });
            }
            break;

          case "alert_created":
            queryClient.invalidateQueries({ queryKey: ["alerts-active"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            break;

          case "heartbeat":
          case "status_change":
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
            queryClient.invalidateQueries({ queryKey: ["health-centers"] });

            if (wsEvent.center_id) {
              queryClient.invalidateQueries({
                queryKey: ["health-center", wsEvent.center_id],
              });
            }
            break;

          case "replication":
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            queryClient.invalidateQueries({ queryKey: ["monitored-databases"] });
            break;

          case "backup":
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });

            if (wsEvent.center_id) {
              queryClient.invalidateQueries({
                queryKey: ["backups", wsEvent.center_id],
              });
            }
            break;

          case "metrics":
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            queryClient.invalidateQueries({ queryKey: ["monitored-databases"] });
            break;

          case "data_ingest":
            // dispatch global event for LiveStreamChart, also bump throughput-related caches
            window.dispatchEvent(
              new CustomEvent("medisoft:data_ingest", {
                detail: {
                  rows: wsEvent.rows ?? wsEvent.payload?.rows ?? 0,
                  bytes: wsEvent.bytes ?? wsEvent.payload?.bytes ?? 0,
                  center_id: wsEvent.center_id,
                },
              })
            );
            break;

          case "sms_sent":
          case "sms_status":
            queryClient.invalidateQueries({ queryKey: ["sms-logs"] });
            break;

          case "ai_diagnosis_ready":
            if (wsEvent.center_id) {
              queryClient.invalidateQueries({ queryKey: ["ai-diagnosis", wsEvent.center_id] });
            }
            break;

          case "source_report":
            queryClient.invalidateQueries({ queryKey: ["centers-live"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
            queryClient.invalidateQueries({ queryKey: ["health-centers"] });
            queryClient.invalidateQueries({ queryKey: ["heartbeat-timeline"] });
            if (wsEvent.center_id) {
              queryClient.invalidateQueries({ queryKey: ["source-report", wsEvent.center_id] });
              queryClient.invalidateQueries({ queryKey: ["health-center", wsEvent.center_id] });
              queryClient.invalidateQueries({ queryKey: ["heartbeat-timeline", wsEvent.center_id] });
            }
            break;

          default:
            invalidateAll();
        }
      } catch {
        console.warn("[WS] Received non-JSON message");
      }
    },
    [queryClient, invalidateAll]
  );

  const connect = useCallback(() => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    try {
      const url = getWsUrl();
      const token = localStorage.getItem("auth_token");
      const ws = new WebSocket(token ? `${url}?token=${token}` : url);

      ws.onopen = () => {
        setConnected(true);
        setUsingPolling(false);
        attemptRef.current = 0;
        console.log("[WS] Connected to monitoring WebSocket");
      };

      ws.onmessage = (e) => handleMessageRef.current(e);

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;

        if (attemptRef.current < maxReconnectAttempts) {
          const delay = Math.min(2000 * Math.pow(2, attemptRef.current), 60000);
          attemptRef.current += 1;
          reconnectTimer.current = setTimeout(() => {
            connectRef.current();
          }, delay);
        } else if (fallbackPolling) {
          console.log("[WS] Max reconnect attempts reached, falling back to polling");
          setUsingPolling(true);
        }
      };

      ws.onerror = () => {
        try { ws.close(); } catch {}
      };

      wsRef.current = ws;
    } catch (error) {
      console.error("[WS] Failed to create WebSocket:", error);
      setConnected(false);

      if (fallbackPolling) {
        setUsingPolling(true);
      }
    }
  }, [getWsUrl, fallbackPolling]);

  // Keep refs current without re-triggering the mount effect
  useEffect(() => {
    handleMessageRef.current = handleMessage;
    connectRef.current = connect;
  }, [handleMessage, connect]);

  useEffect(() => {
    if (!usingPolling) return;

    const id = setInterval(() => {
      invalidateAll();
    }, pollingInterval);

    return () => clearInterval(id);
  }, [usingPolling, pollingInterval, invalidateAll]);

  // Mount once — connect, and tear down on unmount
  useEffect(() => {
    connectRef.current();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
        wsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    connected,
    usingPolling,
    reconnect: () => {
      attemptRef.current = 0;
      setUsingPolling(false);

      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }

      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
        wsRef.current = null;
      }

      connectRef.current();
    },
  };
}