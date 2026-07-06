import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Loader2,
  CheckCircle2,
  Building2,
  Server,
  Phone,
  ShieldCheck,
  X,
  RefreshCw,
  Database,
  MapPin,
  Network,
  ArrowRight,
  Info,
} from "lucide-react";
import { toast } from "sonner";

import { DashboardLayout } from "@/components/DashboardLayout";
import { PageHeader } from "@/components/DashboardWidgets";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchAvailableDatabases,
  registerHealthCenter,
  validateDatabase,
} from "@/lib/api";
import type { RegisterHealthCenterPayload, UnregisteredDatabase } from "@/lib/types";

const PHONE_ROLES = ["Titulaire", "Comptable", "Head of Center", "IT", "Other"];

const initialForm: RegisterHealthCenterPayload = {
  name: "",
  province: "",
  district: "",
  database_name: "",
  foss_id: "",
  replication_channel: "",
  source_host: "",
  source_port: 3306,
  expected_sync_interval: 15,
  anydesk_id: "",
  rustdesk_id: "",
  phone_number_1: "",
  phone_contact_1: "",
  phone_role_1: "Titulaire",
  phone_number_2: "",
  phone_contact_2: "",
  phone_role_2: "Comptable",
  latitude: null,
  longitude: null,
  selected_database_schema: "",
};

type AutoFilledFields = Partial<Record<keyof RegisterHealthCenterPayload, boolean>>;

const RegisterHealthCenter = () => {
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [availableDatabases, setAvailableDatabases] = useState<UnregisteredDatabase[]>([]);
  const [loadingDatabases, setLoadingDatabases] = useState(true);
  const [selectingDatabase, setSelectingDatabase] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [selectedDatabaseSchema, setSelectedDatabaseSchema] = useState("");
  const [showAllDatabases, setShowAllDatabases] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [popupVisible, setPopupVisible] = useState(false);
  const [popupMessage, setPopupMessage] = useState("");
  const popupTimerRef = useRef<number | null>(null);
  const [form, setForm] = useState<RegisterHealthCenterPayload>(initialForm);
  const [autoFilledFields, setAutoFilledFields] = useState<AutoFilledFields>({});

  useEffect(() => {
    void loadAvailableDatabases();

    return () => {
      if (popupTimerRef.current) {
        window.clearTimeout(popupTimerRef.current);
      }
    };
  }, []);

  const loadAvailableDatabases = async () => {
    setLoadingDatabases(true);
    try {
      const res = await fetchAvailableDatabases();
      setAvailableDatabases(Array.isArray(res.data) ? res.data : []);
    } catch (error) {
      console.error(error);
      toast.error("Failed to load available databases.");
    } finally {
      setLoadingDatabases(false);
    }
  };

  const filteredDatabases = useMemo(() => {
    const q = search.trim().toLowerCase();

    if (!q && !showAllDatabases) {
      return [];
    }

    const rows = !q
      ? availableDatabases
      : availableDatabases.filter((db) => {
          const haystacks = [
            db.schema_name,
            db.health_center_name,
            db.replication_channel,
            db.source_host,
            db.province,
            db.district,
            db.foss_id,
            db.match_reason,
          ];
          return haystacks.some((value) => (value || "").toLowerCase().includes(q));
        });

    return rows.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
  }, [availableDatabases, search, showAllDatabases]);

  const selectedDatabaseDetails = useMemo(
    () =>
      availableDatabases.find(
        (db) => (db.schema_name || "") === selectedDatabaseSchema,
      ),
    [availableDatabases, selectedDatabaseSchema],
  );

  const shouldShowDatabaseResults =
    !selectedDatabaseSchema && (search.trim().length > 0 || showAllDatabases);

  const updateField = (field: keyof RegisterHealthCenterPayload, value: string | number) => {
    setForm((prev) => ({
      ...prev,
      [field]: value,
    }));

    setAutoFilledFields((prev) => ({
      ...prev,
      [field]: false,
    }));
  };

  const showSelectionPopup = (message: string) => {
    setPopupMessage(message);
    setPopupVisible(true);

    if (popupTimerRef.current) {
      window.clearTimeout(popupTimerRef.current);
    }

    popupTimerRef.current = window.setTimeout(() => {
      setPopupVisible(false);
    }, 2200);
  };

  const getStatusBadgeClass = (status?: string) => {
    if ((status || "").toUpperCase() === "ON") {
      return "border border-emerald-200 bg-emerald-100 text-emerald-700";
    }
    if ((status || "").toUpperCase() === "OFF") {
      return "border border-red-200 bg-red-100 text-red-700";
    }
    return "border border-slate-200 bg-slate-100 text-slate-700";
  };

  const getMatchBadgeClass = (score?: number) => {
    if ((score || 0) >= 100) {
      return "border border-emerald-200 bg-emerald-100 text-emerald-700";
    }
    if ((score || 0) >= 90) {
      return "border border-cyan-200 bg-cyan-100 text-cyan-700";
    }
    return "border border-amber-200 bg-amber-100 text-amber-700";
  };

  const getMatchLabel = (score?: number) => {
    if ((score || 0) >= 100) return "Excellent match";
    if ((score || 0) >= 90) return "Strong match";
    return "Possible match";
  };

  const getMatchReason = (db?: UnregisteredDatabase | null) => {
    if (!db) return "Match reason not available.";

    if (db.match_reason && String(db.match_reason).trim()) {
      return String(db.match_reason);
    }

    if (db.match_type && String(db.match_type).trim()) {
      return String(db.match_type);
    }

    const score = db.match_score || 0;

    if (score >= 100) {
      return "The discovered database name and health center information match exactly or almost exactly.";
    }
    if (score >= 90) {
      return "Most key details match, but there are small differences such as abbreviations, suffixes, or naming style.";
    }
    return "Some details are similar, but the match is weaker and should be reviewed carefully before registration.";
  };

  const getInputClass = (
    value: string | number | undefined,
    options?: { readOnly?: boolean; autoFilled?: boolean },
  ) => {
    const readOnly = options?.readOnly;
    const autoFilled = options?.autoFilled;

    if (readOnly) {
      return "border-emerald-200 bg-emerald-50 font-medium";
    }

    if (autoFilled) {
      return "border-cyan-200 bg-cyan-50";
    }

    if (typeof value === "number") {
      return value > 0 ? "border-emerald-200 bg-emerald-50" : "";
    }

    if (value && String(value).trim() !== "") {
      return "border-emerald-200 bg-emerald-50";
    }

    return "";
  };

  const handleSelectDatabase = async (database: UnregisteredDatabase) => {
    const schemaName = database.schema_name || "";
    if (!schemaName) return;

    setSelectingDatabase(true);
    setSelectedDatabaseSchema(schemaName);
    setShowForm(false);

    try {
      const res = await validateDatabase(schemaName);
      const data = res.data;

      if (!data?.exists) {
        toast.error("Selected database does not exist.");
        setSelectedDatabaseSchema("");
        return;
      }

      if (data?.already_registered) {
        toast.error("This database is already registered.");
        setSelectedDatabaseSchema("");
        return;
      }

      const prefill = data?.prefill || {};

      const nextForm: RegisterHealthCenterPayload = {
        ...initialForm,
        database_name: schemaName,
        selected_database_schema: schemaName,
        selected_database_details: {
          schema_name: schemaName,
          health_center_name: database.health_center_name,
          province: database.province,
          district: database.district,
          foss_id: database.foss_id,
          replication_channel: database.replication_channel,
          source_host: database.source_host,
          source_port: database.source_port,
          io_thread: database.io_thread,
          sql_thread: database.sql_thread,
          match_score: database.match_score,
          match_type: database.match_type,
          match_reason: database.match_reason,
        },
        name: prefill.name || database.health_center_name || "",
        province: prefill.province || database.province || "",
        district: prefill.district || database.district || "",
        foss_id: prefill.foss_id || database.foss_id || "",
        phone_contact_1: prefill.phone_contact_1 || "",
        phone_contact_2: prefill.phone_contact_2 || "",
        phone_number_1: prefill.phone_number_1 || "",
        phone_number_2: prefill.phone_number_2 || "",
        replication_channel:
          prefill.replication_channel || database.replication_channel || "",
        source_host: prefill.source_host || database.source_host || "",
        source_port: Number(
          prefill.source_port || database.source_port || 3306,
        ),
        expected_sync_interval: Number(prefill.expected_sync_interval || 15),
        anydesk_id: prefill.anydesk_id || "",
        rustdesk_id: prefill.rustdesk_id || "",
      };

      setForm(nextForm);

      setAutoFilledFields({
        name: Boolean(nextForm.name),
        province: Boolean(nextForm.province),
        district: Boolean(nextForm.district),
        database_name: Boolean(nextForm.database_name),
        foss_id: Boolean(nextForm.foss_id),
        replication_channel: Boolean(nextForm.replication_channel),
        source_host: Boolean(nextForm.source_host),
        source_port: Boolean(nextForm.source_port),
        expected_sync_interval: Boolean(nextForm.expected_sync_interval),
        anydesk_id: Boolean(nextForm.anydesk_id),
        rustdesk_id: Boolean(nextForm.rustdesk_id),
        phone_number_1: Boolean(nextForm.phone_number_1),
        phone_contact_1: Boolean(nextForm.phone_contact_1),
        phone_number_2: Boolean(nextForm.phone_number_2),
        phone_contact_2: Boolean(nextForm.phone_contact_2),
      });

      setShowForm(true);
      showSelectionPopup(`Mapped to ${schemaName}`);
      toast.success(`Loaded ${schemaName} into registration form.`);
    } catch (error: any) {
      console.error(error);
      const msg =
        error?.response?.data?.detail || "Failed to validate selected database.";
      toast.error(msg);
      setSelectedDatabaseSchema("");
      setShowForm(false);
    } finally {
      setSelectingDatabase(false);
    }
  };

  const handleClearSelection = () => {
    setSelectedDatabaseSchema("");
    setForm(initialForm);
    setShowForm(false);
    setPopupVisible(false);
    setAutoFilledFields({});
  };

  const validateFormBeforeSubmit = () => {
    if (!selectedDatabaseSchema || !form.database_name) {
      toast.error("Please select a database first.");
      return false;
    }
    if (selectedDatabaseSchema !== form.database_name) {
      toast.error("Selected database mapping is inconsistent. Re-select the database.");
      return false;
    }
    if (!form.name.trim()) {
      toast.error("Health center name is required.");
      return false;
    }
    if (!form.province.trim()) {
      toast.error("Province is required.");
      return false;
    }
    if (!form.district.trim()) {
      toast.error("District is required.");
      return false;
    }
    if (!form.foss_id.trim()) {
      toast.error("FOSA ID is required.");
      return false;
    }
    return true;
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateFormBeforeSubmit()) return;

    setSubmitting(true);
    try {
      await registerHealthCenter({
        ...form,
        selected_database_schema: selectedDatabaseSchema,
        selected_database_details: selectedDatabaseDetails,
      });
      toast.success("Health center registered successfully.");
      navigate("/health-centers");
    } catch (error: any) {
      console.error(error);
      const msg =
        error?.response?.data?.detail || "Failed to register health center.";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <style>{`
          @keyframes popupFadeSlide {
            0% { opacity: 0; transform: translateY(-8px) scale(0.98); }
            12% { opacity: 1; transform: translateY(0) scale(1); }
            88% { opacity: 1; transform: translateY(0) scale(1); }
            100% { opacity: 0; transform: translateY(-8px) scale(0.98); }
          }
          .selection-popup {
            animation: popupFadeSlide 2.2s ease-in-out forwards;
          }
        `}</style>

        <PageHeader
          title="Register Health Center"
          subtitle="Pick the correct discovered database, verify the mapping, then complete registration."
        />

        {popupVisible && (
          <div className="pointer-events-none fixed left-1/2 top-6 z-50 -translate-x-1/2">
            <div className="selection-popup flex items-center gap-3 rounded-2xl border border-emerald-200 bg-white/80 px-5 py-3 shadow-lg backdrop-blur-md">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-100">
                <CheckCircle2 className="h-5 w-5 text-emerald-700" />
              </div>
              <div>
                <p className="text-sm font-semibold text-emerald-900">Database selected</p>
                <p className="text-sm text-emerald-800">{popupMessage}</p>
              </div>
            </div>
          </div>
        )}

        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white">
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4" />
              Discover and map database
            </CardTitle>
          </CardHeader>

          <CardContent className="space-y-4 p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search database, center, host, channel, province, district, or FOSA ID..."
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    if (e.target.value.trim()) {
                      setShowAllDatabases(false);
                    }
                  }}
                  className="pl-10"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => setShowAllDatabases(true)}
                  disabled={loadingDatabases}
                >
                  Show all databases
                </Button>

                <Button
                  variant="outline"
                  onClick={() => void loadAvailableDatabases()}
                  disabled={loadingDatabases}
                >
                  {loadingDatabases ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-2 h-4 w-4" />
                  )}
                  Refresh
                </Button>

                {selectedDatabaseSchema && (
                  <Button variant="ghost" onClick={handleClearSelection}>
                    <X className="mr-2 h-4 w-4" />
                    Clear selection
                  </Button>
                )}
              </div>
            </div>

            {shouldShowDatabaseResults && (
              <div className="rounded-2xl border bg-muted/20">
                {loadingDatabases ? (
                  <div className="flex items-center justify-center gap-2 px-4 py-10 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading databases...
                  </div>
                ) : filteredDatabases.length === 0 ? (
                  <div className="px-4 py-10 text-center text-sm text-muted-foreground">
                    No database match found.
                  </div>
                ) : (
                  <div className="divide-y">
                    {filteredDatabases.map((db) => (
                      <button
                        key={db.schema_name}
                        type="button"
                        onClick={() => void handleSelectDatabase(db)}
                        className="flex w-full flex-col gap-3 px-4 py-4 text-left transition hover:bg-accent/40 md:flex-row md:items-center md:justify-between"
                      >
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold text-card-foreground">
                              {db.schema_name}
                            </span>

                            {db.health_center_name && (
                              <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
                                {db.health_center_name}
                              </span>
                            )}

                            {typeof db.match_score === "number" && (
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${getMatchBadgeClass(
                                  db.match_score,
                                )}`}
                              >
                                Match {db.match_score}%
                              </span>
                            )}

                            <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-[11px] text-slate-700">
                              {getMatchLabel(db.match_score)}
                            </span>
                          </div>

                          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                            <span className="inline-flex items-center gap-1">
                              <MapPin className="h-3 w-3" />
                              {db.province || "—"} / {db.district || "—"}
                            </span>

                            <span className="inline-flex items-center gap-1">
                              <Network className="h-3 w-3" />
                              {db.source_host || "No host"}
                            </span>

                            <span className="inline-flex items-center gap-1">
                              <Server className="h-3 w-3" />
                              {db.replication_channel || "No channel"}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-start gap-2">
                            <span
                              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${getStatusBadgeClass(
                                db.io_thread,
                              )}`}
                            >
                              IO: {db.io_thread || "UNKNOWN"}
                            </span>

                            <span
                              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${getStatusBadgeClass(
                                db.sql_thread,
                              )}`}
                            >
                              SQL: {db.sql_thread || "UNKNOWN"}
                            </span>
                          </div>

                          <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>{getMatchReason(db)}</span>
                          </div>
                        </div>

                        <div className="inline-flex items-center gap-2 text-sm font-medium text-primary">
                          Select <ArrowRight className="h-4 w-4" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedDatabaseSchema && selectedDatabaseDetails && (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border bg-card p-4">
                  <p className="mb-1 text-xs text-muted-foreground">Selected database</p>
                  <p className="font-mono text-sm font-semibold">{selectedDatabaseSchema}</p>
                </div>

                <div className="rounded-2xl border bg-card p-4">
                  <p className="mb-1 text-xs text-muted-foreground">Matched health center</p>
                  <p className="text-sm font-semibold">
                    {selectedDatabaseDetails.health_center_name || form.name || "—"}
                  </p>
                </div>

                <div className="rounded-2xl border bg-card p-4">
                  <p className="mb-1 text-xs text-muted-foreground">Replication host</p>
                  <p className="font-mono text-sm font-semibold">
                    {selectedDatabaseDetails.source_host || form.source_host || "—"}
                  </p>
                </div>

                <div className="rounded-2xl border bg-amber-50 p-4 dark:bg-amber-950/20">
                  <p className="mb-1 text-xs font-medium text-amber-700 dark:text-amber-400">
                    Mapping check
                  </p>
                  <p className="text-sm text-amber-800 dark:text-amber-300">
                    Registration will be saved against <strong>{selectedDatabaseSchema}</strong>,
                    not any other center database.
                  </p>
                </div>
              </div>
            )}

            {selectedDatabaseSchema && selectedDatabaseDetails && (
              <div className="rounded-2xl border border-cyan-200 bg-cyan-50 p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  {typeof selectedDatabaseDetails.match_score === "number" && (
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${getMatchBadgeClass(
                        selectedDatabaseDetails.match_score,
                      )}`}
                    >
                      Match {selectedDatabaseDetails.match_score}%
                    </span>
                  )}

                  <span className="rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs text-slate-700">
                    {getMatchLabel(selectedDatabaseDetails.match_score)}
                  </span>

                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${getStatusBadgeClass(
                      selectedDatabaseDetails.io_thread,
                    )}`}
                  >
                    IO: {selectedDatabaseDetails.io_thread || "UNKNOWN"}
                  </span>

                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${getStatusBadgeClass(
                      selectedDatabaseDetails.sql_thread,
                    )}`}
                  >
                    SQL: {selectedDatabaseDetails.sql_thread || "UNKNOWN"}
                  </span>
                </div>

                <div className="flex items-start gap-2 text-sm text-cyan-900">
                  <Info className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{getMatchReason(selectedDatabaseDetails)}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {selectingDatabase && (
          <div className="rounded-2xl border bg-card px-4 py-3 text-sm text-muted-foreground shadow-sm">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Validating selected database and loading prefill data...
            </div>
          </div>
        )}

        {showForm && (
          <form onSubmit={handleRegister} className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Building2 className="h-4 w-4" /> Health center information
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <Input
                  value={form.name}
                  onChange={(e) => updateField("name", e.target.value)}
                  placeholder="Health center name"
                  className={getInputClass(form.name, { autoFilled: autoFilledFields.name })}
                />

                <Input
                  value={form.province}
                  onChange={(e) => updateField("province", e.target.value)}
                  placeholder="Province"
                  className={getInputClass(form.province, { autoFilled: autoFilledFields.province })}
                />

                <Input
                  value={form.district}
                  onChange={(e) => updateField("district", e.target.value)}
                  placeholder="District"
                  className={getInputClass(form.district, { autoFilled: autoFilledFields.district })}
                />

                <Input
                  value={form.database_name}
                  onChange={(e) => updateField("database_name", e.target.value)}
                  placeholder="Database name"
                  readOnly
                  className={getInputClass(form.database_name, { readOnly: true })}
                />

                <Input
                  value={form.foss_id}
                  onChange={(e) => updateField("foss_id", e.target.value)}
                  placeholder="FOSA ID"
                  className={getInputClass(form.foss_id, { autoFilled: autoFilledFields.foss_id })}
                />

                <Input
                  value={form.expected_sync_interval}
                  onChange={(e) =>
                    updateField("expected_sync_interval", Number(e.target.value || 0))
                  }
                  placeholder="Expected sync interval (sec)"
                  type="number"
                  className={getInputClass(form.expected_sync_interval, {
                    autoFilled: autoFilledFields.expected_sync_interval,
                  })}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Server className="h-4 w-4" /> Replication and remote access
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <Input
                  value={form.replication_channel}
                  onChange={(e) => updateField("replication_channel", e.target.value)}
                  placeholder="Replication channel"
                  className={getInputClass(form.replication_channel, {
                    autoFilled: autoFilledFields.replication_channel,
                  })}
                />

                <Input
                  value={form.source_host}
                  onChange={(e) => updateField("source_host", e.target.value)}
                  placeholder="Source host"
                  className={getInputClass(form.source_host, {
                    autoFilled: autoFilledFields.source_host,
                  })}
                />

                <Input
                  value={form.source_port}
                  onChange={(e) => updateField("source_port", Number(e.target.value || 0))}
                  placeholder="Source port"
                  type="number"
                  className={getInputClass(form.source_port, {
                    autoFilled: autoFilledFields.source_port,
                  })}
                />

                <Input
                  value={form.anydesk_id}
                  onChange={(e) => updateField("anydesk_id", e.target.value)}
                  placeholder="AnyDesk ID"
                  className={getInputClass(form.anydesk_id, {
                    autoFilled: autoFilledFields.anydesk_id,
                  })}
                />

                <Input
                  value={form.rustdesk_id}
                  onChange={(e) => updateField("rustdesk_id", e.target.value)}
                  placeholder="RustDesk ID"
                  className={getInputClass(form.rustdesk_id, {
                    autoFilled: autoFilledFields.rustdesk_id,
                  })}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Phone className="h-4 w-4" /> Contacts
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  Tag every phone with its role (Titulaire / Comptable / …). SMS alerts are routed based on this label.
                </p>
              </CardHeader>
              <CardContent className="space-y-6">
                {([1, 2] as const).map((n) => {
                  const numKey = `phone_number_${n}` as const;
                  const nameKey = `phone_contact_${n}` as const;
                  const roleKey = `phone_role_${n}` as const;
                  return (
                    <div key={n} className="grid gap-3 md:grid-cols-3">
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">
                          Phone number {n}
                        </label>
                        <Input
                          value={(form as any)[numKey] || ""}
                          onChange={(e) => updateField(numKey, e.target.value)}
                          placeholder={`e.g. 07880000${n}0`}
                          className={getInputClass((form as any)[numKey], {
                            autoFilled: (autoFilledFields as any)[numKey],
                          })}
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">
                          Contact name {n}
                        </label>
                        <Input
                          value={(form as any)[nameKey] || ""}
                          onChange={(e) => updateField(nameKey, e.target.value)}
                          placeholder="Full name"
                          className={getInputClass((form as any)[nameKey], {
                            autoFilled: (autoFilledFields as any)[nameKey],
                          })}
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">
                          Role
                        </label>
                        <select
                          value={(form as any)[roleKey] || ""}
                          onChange={(e) => updateField(roleKey as any, e.target.value)}
                          className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                        >
                          {PHONE_ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <MapPin className="h-4 w-4" /> Geo location (for Rwanda map)
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  Optional. If provided, the health center appears as a colored marker on the Operations Center map.
                </p>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                <Input
                  type="number"
                  step="0.0000001"
                  value={form.latitude ?? ""}
                  onChange={(e) => updateField("latitude" as any, e.target.value === "" ? null : Number(e.target.value))}
                  placeholder="Latitude (e.g. -1.9536)"
                />
                <Input
                  type="number"
                  step="0.0000001"
                  value={form.longitude ?? ""}
                  onChange={(e) => updateField("longitude" as any, e.target.value === "" ? null : Number(e.target.value))}
                  placeholder="Longitude (e.g. 30.0606)"
                />
              </CardContent>
            </Card>

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-card px-5 py-4 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-full bg-primary/10 p-2 text-primary">
                  <ShieldCheck className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-sm font-semibold">Final registration target</p>
                  <p className="text-sm text-muted-foreground">
                    This center will be linked to{" "}
                    <span className="font-mono font-medium">
                      {selectedDatabaseSchema || "—"}
                    </span>
                    .
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={handleClearSelection}>
                  Reset
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Register health center
                </Button>
              </div>
            </div>
          </form>
        )}
      </div>
    </DashboardLayout>
  );
};

export default RegisterHealthCenter;