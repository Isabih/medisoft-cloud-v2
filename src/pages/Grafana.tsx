import { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ExternalLink, Settings as SettingsIcon, RefreshCw, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

const DEFAULT_BASE = "http://localhost:3000";

const DASHBOARDS = [
  { id: "overview", uid: "medisoft-overview", label: "Cluster Overview" },
  { id: "replication", uid: "medisoft-replication", label: "Replication Lag" },
  { id: "resources", uid: "medisoft-resources", label: "Resource Heatmap" },
  { id: "per-hc", uid: "medisoft-per-hc", label: "Per-Health-Center" },
];

type Status = "idle" | "checking" | "ok" | "fail";

const GrafanaPage = () => {
  const [base, setBase] = useState(
    () => localStorage.getItem("grafana_base_url") || DEFAULT_BASE
  );
  const [editing, setEditing] = useState(false);
  const [active, setActive] = useState(DASHBOARDS[0].id);
  const [refreshTick, setRefreshTick] = useState(0);
  const [status, setStatus] = useState<Status>("idle");

  const cleanBase = base.replace(/\/$/, "");

  const saveBase = () => {
    localStorage.setItem("grafana_base_url", cleanBase);
    setEditing(false);
    setRefreshTick((n) => n + 1);
  };

  const checkConnection = async () => {
    setStatus("checking");
    try {
      // Grafana /api/health is open even when anonymous viewer is enabled
      const res = await fetch(`${cleanBase}/api/health`, { mode: "no-cors" });
      // no-cors returns opaque — treat as reachable
      setStatus(res ? "ok" : "fail");
    } catch {
      setStatus("fail");
    }
  };

  useEffect(() => {
    checkConnection();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleanBase]);

  const srcFor = (uid: string, id: string) =>
    `${cleanBase}/d/${uid}/${id}?orgId=1&refresh=10s&kiosk&theme=dark&v=${refreshTick}`;

  return (
    <DashboardLayout>
      <PageHeader
        title="Grafana Dashboards"
        subtitle="Embedded Prometheus + Grafana views — replication, resources, throughput, per-center"
      >
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={checkConnection} disabled={status === "checking"}>
            {status === "checking" ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
            Test connection
          </Button>
          <Button size="sm" variant="outline" onClick={() => setRefreshTick((n) => n + 1)}>
            <RefreshCw className="mr-1 h-3.5 w-3.5" /> Reload
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)}>
            <SettingsIcon className="mr-1 h-3.5 w-3.5" /> Configure
          </Button>
          <Button size="sm" variant="outline" asChild>
            <a href={`${cleanBase}/dashboards`} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1 h-3.5 w-3.5" /> Open Grafana
            </a>
          </Button>
        </div>
      </PageHeader>

      {editing && (
        <div className="mb-4 flex flex-col gap-2 rounded-lg border bg-card p-3 sm:flex-row sm:items-center">
          <Input
            value={base}
            onChange={(e) => setBase(e.target.value)}
            placeholder="https://grafana.medisoft.local"
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={saveBase}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => { setBase(DEFAULT_BASE); }}>Reset</Button>
          </div>
        </div>
      )}

      <div className="mb-3 flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Base URL:</span>
        <code className="rounded bg-muted px-1.5 py-0.5">{cleanBase}</code>
        {status === "ok" && <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 className="h-3 w-3" /> reachable</span>}
        {status === "fail" && <span className="inline-flex items-center gap-1 text-destructive"><AlertTriangle className="h-3 w-3" /> unreachable</span>}
      </div>

      {status === "fail" && (
        <Alert variant="destructive" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Grafana is not reachable at {cleanBase}</AlertTitle>
          <AlertDescription className="text-xs">
            1. Start the stack: <code className="rounded bg-background/50 px-1">cd backend/grafana &amp;&amp; docker compose -f docker-compose.grafana.yml up -d</code><br />
            2. Make sure <code>GF_SECURITY_ALLOW_EMBEDDING=true</code> and <code>GF_AUTH_ANONYMOUS_ENABLED=true</code> are set.<br />
            3. If Grafana runs on another machine, click <b>Configure</b> and set its public URL (e.g. <code>https://grafana.your-domain.com</code>).<br />
            4. For cloud previews, Grafana must be served over <b>HTTPS on a public domain</b> — browsers will block <code>http://localhost</code> iframes here.
          </AlertDescription>
        </Alert>
      )}

      <Tabs value={active} onValueChange={setActive}>
        <TabsList>
          {DASHBOARDS.map((d) => (
            <TabsTrigger key={d.id} value={d.id}>{d.label}</TabsTrigger>
          ))}
        </TabsList>
        {DASHBOARDS.map((d) => (
          <TabsContent key={d.id} value={d.id}>
            <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
              {active === d.id ? (
                <iframe
                  key={`${d.id}-${refreshTick}`}
                  src={srcFor(d.uid, d.id)}
                  title={d.label}
                  className="h-[78vh] w-full border-0"
                  sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                />
              ) : (
                <div className="h-[78vh] w-full" />
              )}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Dashboard UID: <code className="rounded bg-muted px-1">{d.uid}</code>.
              See <code>backend/grafana/README.md</code> and <code>INSTALL_GUIDE.md</code> for full setup.
            </p>
          </TabsContent>
        ))}
      </Tabs>
    </DashboardLayout>
  );
};

export default GrafanaPage;
