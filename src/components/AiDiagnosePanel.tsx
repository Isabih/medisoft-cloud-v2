import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Brain, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { aiDiagnose } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  centerId: string;
  context?: Record<string, unknown>;
  auto?: boolean;
}

interface Diagnosis {
  root_cause: string;
  fix_steps: string[];
  severity: "info" | "warning" | "critical";
  auto_healable: boolean;
  first_aid_actions?: string[];
  supported_dashboard_actions?: { key: string; label: string; available_now: boolean }[];
  future_version_actions?: string[];
  mode?: string;
}

export function AiDiagnosePanel({ centerId, context, auto = false }: Props) {
  const [loading, setLoading] = useState(false);
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await aiDiagnose(centerId, context);
      setDiag(res.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "AI diagnosis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Brain className="h-4 w-4 text-primary" />
            AI Diagnosis
          </div>
          <Button size="sm" variant="outline" onClick={run} disabled={loading}>
            {loading ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
            {diag ? "Re-diagnose" : "Diagnose now"}
          </Button>
        </div>

        {err && (
          <p className="rounded-md bg-destructive/10 p-2 text-xs text-destructive">
            {err}
          </p>
        )}

        {!diag && !err && !loading && (
          <p className="text-xs text-muted-foreground">
            Click "Diagnose now" to ask AI what's wrong and how to fix it.
          </p>
        )}

        {diag && (
          <div className="space-y-3 text-sm">
            <div
              className={cn(
                "flex items-start gap-2 rounded-md p-2",
                diag.severity === "critical"
                  ? "bg-destructive/10 text-destructive"
                  : diag.severity === "warning"
                  ? "bg-warning/10 text-warning"
                  : "bg-muted text-muted-foreground"
              )}
            >
              {diag.severity === "critical" ? (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <div>
                <p className="text-xs font-semibold uppercase">Root cause</p>
                <p className="mt-0.5 text-sm">{diag.root_cause}</p>
              </div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                Fix steps
              </p>
              <ol className="list-inside list-decimal space-y-1 text-sm">
                {diag.fix_steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </div>



            {diag.first_aid_actions && diag.first_aid_actions.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                  First Aid actions
                </p>
                <ul className="list-inside list-disc space-y-1 text-sm">
                  {diag.first_aid_actions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {diag.supported_dashboard_actions && diag.supported_dashboard_actions.length > 0 && (
              <div className="rounded-md bg-success/10 p-2 text-xs text-success">
                Available now: {diag.supported_dashboard_actions.map((a) => a.label).join(", ")}
              </div>
            )}

            {diag.future_version_actions && diag.future_version_actions.length > 0 && (
              <div className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
                Future version: {diag.future_version_actions.join(", ")}
              </div>
            )}

            {diag.auto_healable && (
              <p className="rounded-md bg-success/10 p-2 text-xs text-success">
                ✓ This issue is auto-healable — use the First Aid buttons.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
