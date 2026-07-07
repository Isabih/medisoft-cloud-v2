import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthProvider";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { createAppQueryClient } from "@/lib/query";
import LoginPage from "./pages/Login";
import DashboardPage from "./pages/Dashboard";
import HealthCentersPage from "./pages/HealthCenters";
import HealthCenterDetail from "./pages/HealthCenterDetail";
import RegisterHealthCenter from "./pages/RegisterHealthCenter";
import ReportsPage from "./pages/Reports";
import SettingsPage from "./pages/Settings";
import MonitoringPage from "./pages/Monitoring";
import AlertsPage from "./pages/Alerts";
import SmsLogsPage from "./pages/SmsLogs";
import GrafanaPage from "./pages/Grafana";
import InstallersPage from "./pages/Installers";
import AuditLogsPage from "./pages/AuditLogs";
import SystemHealthPage from "./pages/SystemHealth";
import OperationsCenter from "./pages/OperationsCenter";
import NotFound from "./pages/NotFound";

const queryClient = createAppQueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter basename="/v3">
          <Routes>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
            <Route path="/operations" element={<ProtectedRoute><OperationsCenter /></ProtectedRoute>} />
            <Route path="/health-centers" element={<ProtectedRoute><HealthCentersPage /></ProtectedRoute>} />
            <Route path="/health-centers/register" element={<ProtectedRoute><RegisterHealthCenter /></ProtectedRoute>} />
            <Route path="/health-centers/:id" element={<ProtectedRoute><HealthCenterDetail /></ProtectedRoute>} />
            <Route path="/monitoring" element={<ProtectedRoute><MonitoringPage /></ProtectedRoute>} />
            <Route path="/alerts" element={<ProtectedRoute><AlertsPage /></ProtectedRoute>} />
            <Route path="/sms-logs" element={<ProtectedRoute><SmsLogsPage /></ProtectedRoute>} />
            <Route path="/grafana" element={<ProtectedRoute><GrafanaPage /></ProtectedRoute>} />
            <Route path="/reports" element={<ProtectedRoute><ReportsPage /></ProtectedRoute>} />
            <Route path="/installers" element={<ProtectedRoute><InstallersPage /></ProtectedRoute>} />
            <Route path="/audit-logs" element={<ProtectedRoute><AuditLogsPage /></ProtectedRoute>} />
            <Route path="/system-health" element={<ProtectedRoute><SystemHealthPage /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
