import { useState, useEffect } from "react";

const DEFAULT_API_BASE_URL = "http://100.115.244.88/api/v1";

export function useServerStatus(pollInterval = 60000) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  useEffect(() => {
    let active = true;

    const check = async () => {
      try {
        const baseUrl =
          localStorage.getItem("api_base_url") || DEFAULT_API_BASE_URL;

        const res = await fetch(`${baseUrl}/health`, {
          method: "GET",
          signal: AbortSignal.timeout(5000),
        });

        if (active) {
          setApiReachable(res.ok);
        }
      } catch {
        if (active) {
          setApiReachable(false);
        }
      }
    };

    check();
    const id = setInterval(check, pollInterval);

    return () => {
      active = false;
      clearInterval(id);
    };
  }, [pollInterval]);

  return { isOnline, apiReachable };
}