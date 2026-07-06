import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Wand2, Loader2 } from "lucide-react";
import { autoHealChannel } from "@/lib/api";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

interface Props {
  channelName?: string | null;
  centerId?: string;
  centerName?: string;
  size?: "sm" | "default" | "lg";
  variant?: "default" | "outline" | "ghost";
}

export function AutoHealButton({
  channelName,
  centerId,
  centerName,
  size = "sm",
  variant = "outline",
}: Props) {
  const [loading, setLoading] = useState(false);
  const qc = useQueryClient();

  const onHeal = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!channelName) {
      toast.error("No replication channel configured for this center.");
      return;
    }
    setLoading(true);
    const t = toast.loading(`Healing ${centerName || channelName}…`);
    try {
      const res = await autoHealChannel(channelName);
      toast.dismiss(t);
      const ok = res.data?.success ?? true;
      const steps = res.data?.steps_taken?.join(" → ") || "Auto-heal completed";
      if (ok) toast.success(`${centerName || channelName}: ${steps}`);
      else toast.error(`Heal failed: ${res.data?.detail || "see logs"}`);
      qc.invalidateQueries({ queryKey: ["centers-live"] });
      if (centerId) qc.invalidateQueries({ queryKey: ["health-center", centerId] });
    } catch (err: any) {
      toast.dismiss(t);
      toast.error(err?.response?.data?.detail || "Auto-heal failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      size={size}
      variant={variant}
      onClick={onHeal}
      disabled={loading || !channelName}
      title={channelName ? `Auto-heal ${channelName}` : "No replication channel"}
    >
      {loading ? (
        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
      ) : (
        <Wand2 className="mr-1 h-3.5 w-3.5" />
      )}
      Auto-Heal
    </Button>
  );
}
