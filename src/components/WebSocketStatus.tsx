import { Wifi, WifiOff, Radio, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface WebSocketStatusProps {
  connected: boolean;
  usingPolling: boolean;
  onReconnect: () => void;
}

export function WebSocketStatus({ connected, usingPolling, onReconnect }: WebSocketStatusProps) {
  return (
    <div className="flex items-center gap-2">
      {connected ? (
        <>
          <Radio className="w-3.5 h-3.5 text-success" />
          <span className="text-xs text-sidebar-foreground/60">WebSocket Live</span>
          <div className="w-2 h-2 rounded-full ml-auto bg-success animate-pulse" />
        </>
      ) : usingPolling ? (
        <>
          <RefreshCw className="w-3.5 h-3.5 text-warning" />
          <span className="text-xs text-sidebar-foreground/60">Polling (15s)</span>
          <button
            onClick={onReconnect}
            className="ml-auto text-[10px] text-sidebar-foreground/40 hover:text-sidebar-foreground transition-colors underline"
          >
            Retry WS
          </button>
        </>
      ) : (
        <>
          <WifiOff className="w-3.5 h-3.5 text-destructive" />
          <span className="text-xs text-sidebar-foreground/60">Connecting...</span>
          <div className="w-2 h-2 rounded-full ml-auto bg-warning animate-pulse" />
        </>
      )}
    </div>
  );
}
