import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download, Server, ShieldCheck, Database, Copy, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

const API_BASE_URL =
  localStorage.getItem("api_base_url") || "http://127.0.0.1:8000/api/v1";

const installers = [
  {
    kind: "local-agent",
    title: "Local Agent",
    description:
      "Installs the Medisoft Local Agent as a systemd service. Pushes resource & replica metrics every 30s to the central server.",
    icon: Server,
    accent: "from-primary/20 to-primary/5",
  },
  {
    kind: "guardian",
    title: "Replica Guardian",
    description:
      "Watchdog that monitors replication channels and applies safe auto-heal commands when STOP/IO/SQL errors appear.",
    icon: ShieldCheck,
    accent: "from-emerald-500/20 to-emerald-500/5",
  },
  {
    kind: "replication",
    title: "Replication Setup",
    description:
      "Hardened file/position replication installer. Run once on a fresh health-center server to bootstrap the MySQL replica link.",
    icon: Database,
    accent: "from-amber-500/20 to-amber-500/5",
  },
] as const;

export default function InstallersPage() {
  const [copied, setCopied] = useState<string | null>(null);

  const copyOneLiner = (kind: string) => {
    const url = `${API_BASE_URL}/installer/${kind}`;
    const cmd = `curl -fsSL ${url} -o /tmp/${kind}.sh && sudo bash /tmp/${kind}.sh`;
    navigator.clipboard.writeText(cmd);
    setCopied(kind);
    toast.success("Install command copied");
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 page-enter">
        <PageHeader
          title="Installers"
          subtitle="One-click installers for the on-site agents. Copy the command and run it on the target server."
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {installers.map((i) => {
            const Icon = i.icon;
            return (
              <Card key={i.kind} className="card-lift overflow-hidden border">
                <div className={`h-1 w-full bg-gradient-to-r ${i.accent}`} />
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Icon className="h-4 w-4 text-primary" />
                    {i.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">{i.description}</p>

                  <div className="rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed">
                    curl -fsSL {API_BASE_URL}/installer/{i.kind} \<br />
                    {"  "}-o /tmp/{i.kind}.sh && sudo bash /tmp/{i.kind}.sh
                  </div>

                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => copyOneLiner(i.kind)}
                    >
                      {copied === i.kind ? (
                        <>
                          <CheckCircle2 className="mr-2 h-3.5 w-3.5" /> Copied
                        </>
                      ) : (
                        <>
                          <Copy className="mr-2 h-3.5 w-3.5" /> Copy command
                        </>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      className="flex-1"
                      onClick={() => {
                        window.location.href = `${API_BASE_URL}/installer/${i.kind}`;
                      }}
                    >
                      <Download className="mr-2 h-3.5 w-3.5" /> Download .sh
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Suggested order</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>
              1.&nbsp; <b>Replication Setup</b> — bootstraps file/position
              replication and creates the replication user.
            </p>
            <p>
              2.&nbsp; <b>Replica Guardian</b> — watchdog service that catches
              IO/SQL errors and auto-heals safe ones.
            </p>
            <p>
              3.&nbsp; <b>Local Agent</b> — keeps pushing telemetry and applies
              remote actions queued from the dashboard.
            </p>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
