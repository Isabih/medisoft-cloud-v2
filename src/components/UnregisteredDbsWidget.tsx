import { useQuery } from "@tanstack/react-query";
import { Database, AlertTriangle, ChevronRight, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { fetchAvailableDatabases } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const UnregisteredDbsWidget = () => {
  const { data = [], isLoading } = useQuery({
    queryKey: ["available-databases-widget"],
    queryFn: async () => (await fetchAvailableDatabases()).data,
    refetchInterval: 30000,
  });

  const topTwo = data.slice(0, 2);
  const remaining = data.length - topTwo.length;

  return (
    <Card className="rounded-2xl shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <AlertTriangle className="h-4 w-4 text-warning" />
          Unregistered Databases
        </CardTitle>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : topTwo.length === 0 ? (
          <div className="rounded-xl border border-dashed p-6 text-center">
            <Database className="mx-auto mb-2 h-8 w-8 text-muted-foreground/30" />
            <p className="text-sm font-medium text-card-foreground">
              No unregistered databases
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Everything currently available has already been registered.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {topTwo.map((db: any, index: number) => {
              const schemaName = db.schema_name || "—";
              const displayName =
                db.health_center_name ||
                db.name ||
                db.schema_name ||
                "Unnamed database";

              return (
                <div
                  key={`${schemaName}-${index}`}
                  className="rounded-xl border p-3 transition hover:bg-muted/30"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-card-foreground">
                        {displayName}
                      </p>
                      <p className="truncate text-xs font-mono text-muted-foreground">
                        {schemaName}
                      </p>

                      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                        <p>Channel: {db.replication_channel || "—"}</p>
                        <p>Host: {db.source_host || "—"}</p>
                        <p>
                          Location: {db.province || "—"} / {db.district || "—"}
                        </p>
                      </div>
                    </div>

                    <Button size="sm" asChild className="shrink-0">
                      <Link to="/health-centers/register">Register</Link>
                    </Button>
                  </div>
                </div>
              );
            })}

            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-muted-foreground">
                Showing {topTwo.length} of {data.length}
                {remaining > 0 ? ` • ${remaining} more` : ""}
              </p>

              <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" asChild>
                <Link to="/health-centers/register">
                  View all
                  <ChevronRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export { UnregisteredDbsWidget };