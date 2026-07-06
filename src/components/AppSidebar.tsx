import { NavLink } from "@/components/NavLink";
import { useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Building2,
  FileText,
  Settings,
  LogOut,
  Wifi,
  WifiOff,
  Server,
  Activity,
  Bell,
  MessageSquare,
  BarChart3,
  Download,
  History,
  HeartPulse,
  Command,
} from "lucide-react";
import { useServerStatus } from "@/hooks/use-server-status";
import { useAuth } from "@/hooks/use-auth";
import { useWebSocket } from "@/hooks/use-websocket";
import { WebSocketStatus } from "@/components/WebSocketStatus";
import medisoftLogo from "@/assets/medisoft-logo.png";

const navItems = [
  { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
  { title: "Operations", url: "/operations", icon: Command },
  { title: "Health Centers", url: "/health-centers", icon: Building2 },
  { title: "Monitoring", url: "/monitoring", icon: Activity },
  { title: "Alerts", url: "/alerts", icon: Bell },
  { title: "SMS Logs", url: "/sms-logs", icon: MessageSquare },
  { title: "Installers", url: "/installers", icon: Download },
  { title: "Grafana", url: "/grafana", icon: BarChart3 },
  { title: "Reports", url: "/reports", icon: FileText },
  { title: "Audit Log", url: "/audit-logs", icon: History },
  { title: "System Health", url: "/system-health", icon: HeartPulse },
  { title: "Settings", url: "/settings", icon: Settings },
];

export function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isOnline, apiReachable } = useServerStatus();
  const { logout, user } = useAuth();
  const { connected, usingPolling, reconnect } = useWebSocket();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside className="w-60 min-h-screen gradient-sidebar flex flex-col border-r border-sidebar-border">
      {/* Logo */}
      <div className="p-5 border-b border-sidebar-border">
        <div className="flex items-center gap-3">
          <img src={medisoftLogo} alt="Medisoft" className="w-10 h-10 rounded-lg object-contain bg-white/10 p-0.5" />
          <div>
            <h1 className="text-base font-bold text-sidebar-foreground">Medisoft Cloud</h1>
            <p className="text-[10px] text-sidebar-foreground/60 leading-tight">Data Sync Monitor</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item, i) => {
          const isActive = location.pathname.startsWith(item.url);
          return (
            <NavLink
              key={item.url}
              to={item.url}
              end={item.url === "/dashboard"}
              className={`group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 animate-fade-in ${
                isActive
                  ? "gradient-primary text-primary-foreground shadow-lg shadow-primary/20 scale-[1.02]"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground hover:translate-x-0.5"
              }`}
              activeClassName=""
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <item.icon className={`w-4 h-4 transition-transform ${isActive ? "" : "group-hover:scale-110"}`} />
              <span>{item.title}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Status */}
      <div className="p-4 border-t border-sidebar-border space-y-2">
        <div className="flex items-center gap-2">
          {isOnline ? (
            <Wifi className="w-3.5 h-3.5 text-success" />
          ) : (
            <WifiOff className="w-3.5 h-3.5 text-destructive" />
          )}
          <span className="text-xs text-sidebar-foreground/60">
            Internet: {isOnline ? "Connected" : "Disconnected"}
          </span>
          <div className={`w-2 h-2 rounded-full ml-auto ${isOnline ? "bg-success animate-pulse" : "bg-destructive"}`} />
        </div>
        <div className="flex items-center gap-2">
          <Server className="w-3.5 h-3.5 text-sidebar-foreground/40" />
          <span className="text-xs text-sidebar-foreground/60">
            Server: {apiReachable === null ? "Checking…" : apiReachable ? "Online" : "Unreachable"}
          </span>
          <div className={`w-2 h-2 rounded-full ml-auto ${apiReachable === null ? "bg-muted-foreground" : apiReachable ? "bg-success" : "bg-destructive"}`} />
        </div>
        <WebSocketStatus connected={connected} usingPolling={usingPolling} onReconnect={reconnect} />
      </div>

      {/* Logout */}
      <div className="p-3 border-t border-sidebar-border">
        {user && (
          <p className="text-xs text-sidebar-foreground/50 px-3 mb-2 truncate">{user.username} ({user.role})</p>
        )}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-all w-full"
        >
          <LogOut className="w-4 h-4" />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
}
