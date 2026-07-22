import { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Save, MessageSquare, Activity, Loader2, Send, ShieldCheck, Mail, Database, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { fetchSettings, updateSettings, sendTestSms, sendTestEmail, fetchRetentionStatus, runRetentionCleanup, API_BASE_URL } from "@/lib/api";

interface SettingsState {
  day_close_time?: string;
  auto_generate_reports?: boolean;
  polling_interval?: number;
  heartbeat_timeout_seconds?: number;
  backup_check_time?: string;
  sms_provider?: string;
  sms_api_url?: string;
  sms_sender_id?: string;
  sms_username?: string;
  sms_password?: string;     // masked from backend
  sms_password_set?: boolean;
  admin_phone_numbers?: string;
  admin_emails?: string;
  resend_api_key?: string;
  resend_api_key_set?: boolean;
  alert_email_from?: string;
  detailed_retention_days?: number;
  incident_history_retention_days?: number;
  retention_run_hour_utc?: number;
  enable_retention_cleanup?: boolean;
}

const SettingsPage = () => {
  const [data, setData] = useState<SettingsState>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [newResendKey, setNewResendKey] = useState("");
  const [testEmail, setTestEmail] = useState("");
  const [testingEmail, setTestingEmail] = useState(false);
  const [retentionStatus, setRetentionStatus] = useState<any>(null);
  const [runningRetention, setRunningRetention] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((res) => setData(res.data || {}))
      .catch(() => toast.error("Could not load settings from backend"))
      .finally(() => setLoading(false));
    fetchRetentionStatus().then((res) => setRetentionStatus(res.data)).catch(() => null);
  }, []);

  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) =>
    setData((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = { ...data };
      // Only send a password if the user typed a new one.
      delete payload.sms_password;
      delete payload.sms_password_set;
      delete payload.resend_api_key;
      delete payload.resend_api_key_set;
      if (newPassword) payload.sms_password = newPassword;
      if (newResendKey) payload.resend_api_key = newResendKey;

      const res = await updateSettings(payload);
      setData(res.data || {});
      setNewPassword("");
      setNewResendKey("");
      toast.success("Settings saved");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

const handleTestSms = async () => {
  if (!testTo) {
    toast.error("Enter a phone number to test (e.g. 250788592987)");
    return;
  }

  setTesting(true);

  try {
    const res = await sendTestSms(testTo);

    const data = res.data || {};

    if (data.success === true) {
      toast.success(`Test SMS sent successfully to ${testTo}`);
      return;
    }

    const gatewayText = String(
      data.reason ||
      data.gateway_response ||
      data.error ||
      ""
    );

    const normalized = gatewayText.toLowerCase();

    if (
      normalized.includes("exceed your account balance") ||
      normalized.includes("insufficient balance") ||
      normalized.includes('"error":"balance"') ||
      normalized.includes('"error": "balance"')
    ) {
      toast.error("SMS failed: Insufficient InTouch SMS balance.");
    } else if (gatewayText) {
      toast.error(`SMS failed: ${gatewayText}`);
    } else {
      toast.error("SMS gateway reported failure.");
    }

  } catch (e: any) {
    toast.error(
      e?.response?.data?.detail ||
      "Could not reach SMS gateway"
    );
  } finally {
    setTesting(false);
  }
};

  const handleTestEmail = async () => {
    if (!testEmail) {
      toast.error("Enter an email address to test");
      return;
    }
    setTestingEmail(true);
    try {
      const res = await sendTestEmail(testEmail);
      if (res.data?.status === "sent") toast.success(`Test email sent to ${testEmail}`);
      else toast.error(res.data?.error || "Email provider reported failure");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Could not send test email");
    } finally {
      setTestingEmail(false);
    }
  };


  const handleRunRetention = async () => {
    setRunningRetention(true);
    try {
      const res = await runRetentionCleanup();
      toast.success(`Retention cleanup finished: ${res.data?.rows_deleted ?? 0} rows deleted, ${res.data?.incidents_upserted ?? 0} incidents preserved`);
      const status = await fetchRetentionStatus();
      setRetentionStatus(status.data);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Retention cleanup failed");
    } finally {
      setRunningRetention(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <PageHeader title="Settings" subtitle="System configuration and SMS gateway" />

      <Tabs defaultValue="general" className="space-y-6">
        <TabsList>
          <TabsTrigger value="general"><Activity className="w-4 h-4 mr-2" /> General</TabsTrigger>
          <TabsTrigger value="sms"><MessageSquare className="w-4 h-4 mr-2" /> SMS Gateway</TabsTrigger>
          <TabsTrigger value="email"><Mail className="w-4 h-4 mr-2" /> Email Alerts</TabsTrigger>
          <TabsTrigger value="retention"><Database className="w-4 h-4 mr-2" /> Retention</TabsTrigger>
          <TabsTrigger value="api"><ShieldCheck className="w-4 h-4 mr-2" /> API</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-6">
          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold">Polling & Timeouts</h3>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Polling interval (seconds)</Label>
                <Input type="number" value={data.polling_interval ?? 30}
                  onChange={(e) => update("polling_interval", Number(e.target.value))} />
              </div>
              <div>
                <Label>Heartbeat timeout (seconds)</Label>
                <Input type="number" value={data.heartbeat_timeout_seconds ?? 120}
                  onChange={(e) => update("heartbeat_timeout_seconds", Number(e.target.value))} />
              </div>
              <div>
                <Label>Day closing time</Label>
                <Input type="time" value={(data.day_close_time || "00:00:00").slice(0,5)}
                  onChange={(e) => update("day_close_time", `${e.target.value}:00`)} />
              </div>
              <div>
                <Label>Backup check time</Label>
                <Input type="time" value={(data.backup_check_time || "07:00:00").slice(0,5)}
                  onChange={(e) => update("backup_check_time", `${e.target.value}:00`)} />
              </div>
            </div>
            <div className="flex items-center justify-between border-t pt-4">
              <div>
                <Label>Auto-generate daily report</Label>
                <p className="text-xs text-muted-foreground">Run report generation at day closing time</p>
              </div>
              <Switch checked={!!data.auto_generate_reports}
                onCheckedChange={(v) => update("auto_generate_reports", v)} />
            </div>
          </section>
        </TabsContent>

        <TabsContent value="sms" className="space-y-6">
          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <div>
              <h3 className="text-sm font-semibold">Intouch Rwanda SMS Gateway</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Used to notify the head of each health center and system admins when a local
                server is unreachable or replication fails.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>API URL</Label>
                <Input value={data.sms_api_url ?? "https://intouchsms.co.rw"}
                  onChange={(e) => update("sms_api_url", e.target.value)} />
              </div>
              <div>
                <Label>Sender ID / Name</Label>
                <Input placeholder="MEDISOFT" value={data.sms_sender_id ?? ""}
                  onChange={(e) => update("sms_sender_id", e.target.value)} />
              </div>
              <div>
                <Label>Username</Label>
                <Input value={data.sms_username ?? ""}
                  onChange={(e) => update("sms_username", e.target.value)} />
              </div>
              <div>
                <Label>Password {data.sms_password_set && <span className="text-xs text-success ml-1">(set)</span>}</Label>
                <Input type="password" placeholder={data.sms_password_set ? "Leave blank to keep current" : "Enter password"}
                  value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <Label>Admin phone numbers</Label>
                <Input placeholder="250788000000,250722000000"
                  value={data.admin_phone_numbers ?? ""}
                  onChange={(e) => update("admin_phone_numbers", e.target.value)} />
                <p className="text-xs text-muted-foreground mt-1">
                  Comma-separated E.164-style numbers. These receive every critical alert.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-3">
            <h3 className="text-sm font-semibold">Send test SMS</h3>
            <div className="flex flex-col sm:flex-row gap-2">
              <Input placeholder="Phone number e.g. 250788000000"
                value={testTo} onChange={(e) => setTestTo(e.target.value)} />
              <Button onClick={handleTestSms} disabled={testing} variant="secondary">
                {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                Send Test
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Save your settings first, then test. The result is also recorded in SMS Logs.
            </p>
          </section>
        </TabsContent>


        <TabsContent value="email" className="space-y-6">
          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <div>
              <h3 className="text-sm font-semibold">Resend Email Alerts</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Used to notify Medisoft admins when SQL, IO, MySQL, or local server reachability fails.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Sender email</Label>
                <Input placeholder="Medisoft <alerts@yourdomain.rw>" value={data.alert_email_from ?? ""}
                  onChange={(e) => update("alert_email_from", e.target.value)} />
              </div>
              <div>
                <Label>Resend API key {data.resend_api_key_set && <span className="text-xs text-success ml-1">(set)</span>}</Label>
                <Input type="password" placeholder={data.resend_api_key_set ? "Leave blank to keep current" : "re_..."}
                  value={newResendKey} onChange={(e) => setNewResendKey(e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <Label>Admin emails</Label>
                <Input placeholder="admin@medisoft.rw,ops@medisoft.rw" value={data.admin_emails ?? ""}
                  onChange={(e) => update("admin_emails", e.target.value)} />
                <p className="text-xs text-muted-foreground mt-1">
                  Comma-separated emails. These receive critical system and replica alerts.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-3">
            <h3 className="text-sm font-semibold">Send test email</h3>
            <div className="flex flex-col sm:flex-row gap-2">
              <Input placeholder="admin@example.com" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} />
              <Button onClick={handleTestEmail} disabled={testingEmail} variant="secondary">
                {testingEmail ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                Send Test
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Save your Resend settings first, then test.</p>
          </section>
        </TabsContent>



        <TabsContent value="retention" className="space-y-6">
          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <div>
              <h3 className="text-sm font-semibold">Monitoring Retention Policy</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Keep raw monitoring data short-term to avoid database growth, while preserving compact incident history for 3+ month reports.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label>Detailed monitoring days</Label>
                <Input type="number" min={1} max={30} value={data.detailed_retention_days ?? 7}
                  onChange={(e) => update("detailed_retention_days", Number(e.target.value))} />
                <p className="text-xs text-muted-foreground mt-1">Recommended: 7 days.</p>
              </div>
              <div>
                <Label>Incident history days</Label>
                <Input type="number" min={90} max={1095} value={data.incident_history_retention_days ?? 365}
                  onChange={(e) => update("incident_history_retention_days", Number(e.target.value))} />
                <p className="text-xs text-muted-foreground mt-1">Keeps small offline/failure history.</p>
              </div>
              <div>
                <Label>Cleanup hour UTC</Label>
                <Input type="number" min={0} max={23} value={data.retention_run_hour_utc ?? 2}
                  onChange={(e) => update("retention_run_hour_utc", Number(e.target.value))} />
                <p className="text-xs text-muted-foreground mt-1">Runs daily after backend starts.</p>
              </div>
            </div>
            <div className="flex items-center justify-between border-t pt-4">
              <div>
                <Label>Enable automatic cleanup</Label>
                <p className="text-xs text-muted-foreground">Delete raw data older than the detailed monitoring window.</p>
              </div>
              <Switch checked={data.enable_retention_cleanup !== false}
                onCheckedChange={(v) => update("enable_retention_cleanup", v)} />
            </div>
          </section>

          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-semibold">Retention Status</h3>
                <p className="text-xs text-muted-foreground">Manual cleanup first converts old failures into incident history, then deletes raw monitoring rows.</p>
              </div>
              <Button variant="secondary" disabled={runningRetention} onClick={handleRunRetention}>
                {runningRetention ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />}
                Run Cleanup Now
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg bg-muted p-3">
                <p className="text-xs text-muted-foreground">Latest run</p>
                <p className="text-sm font-semibold">{retentionStatus?.latest_run?.status ?? "No run yet"}</p>
              </div>
              <div className="rounded-lg bg-muted p-3">
                <p className="text-xs text-muted-foreground">Rows deleted</p>
                <p className="text-sm font-semibold">{retentionStatus?.latest_run?.rows_deleted ?? 0}</p>
              </div>
              <div className="rounded-lg bg-muted p-3">
                <p className="text-xs text-muted-foreground">Incidents preserved</p>
                <p className="text-sm font-semibold">{retentionStatus?.latest_run?.incidents_upserted ?? 0}</p>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-2 text-xs">
              {Object.entries(retentionStatus?.table_counts || {}).map(([name, count]) => (
                <div key={name} className="flex justify-between rounded bg-muted/60 px-3 py-2">
                  <span>{name}</span><span className="font-semibold">{String(count ?? "n/a")}</span>
                </div>
              ))}
            </div>
          </section>
        </TabsContent>

        <TabsContent value="api" className="space-y-6">
          <section className="rounded-xl border bg-card p-6 shadow-sm space-y-3">
            <h3 className="text-sm font-semibold">Backend API</h3>
            <div className="grid gap-1">
              <Label>Currently connected to</Label>
              <code className="text-xs px-3 py-2 rounded bg-muted">{API_BASE_URL}</code>
              <p className="text-xs text-muted-foreground">
                Override at runtime by setting <code>localStorage.api_base_url</code> in the browser
                console, or at build time with <code>VITE_API_BASE_URL</code>.
              </p>
            </div>
          </section>
        </TabsContent>
      </Tabs>

      <div className="mt-6">
        <Button onClick={handleSave} disabled={saving} className="gradient-primary text-primary-foreground">
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
          Save Settings
        </Button>
      </div>
    </DashboardLayout>
  );
};

export default SettingsPage;
