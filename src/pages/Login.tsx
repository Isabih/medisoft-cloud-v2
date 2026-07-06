import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Lock, User, LogIn, CheckCircle2, Database, Shield, BarChart3, Cloud, Loader2, AlertTriangle } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { toast } from "sonner";
import { fetchSystemHealthCheck } from "@/lib/api";
import mohLogo from "@/assets/moh-logo.png";
import medisoftLogo from "@/assets/medisoft-logo.png";
import dynasoftLogo from "@/assets/dynasoft-logo.jpg";

const LoginPage = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [criticalIssues, setCriticalIssues] = useState<string[]>([]);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);

  useEffect(() => {
    fetchSystemHealthCheck()
      .then((res) => {
        setBackendReachable(true);
        const checks = res.data?.checks || {};
        const issues: string[] = [];
        for (const [name, value] of Object.entries<any>(checks)) {
          if (value && value.ok === false) {
            const reason = value.error || value.hint || (value.missing?.length ? `missing: ${value.missing.join(", ")}` : "not configured");
            issues.push(`${name.replace(/_/g, " ")}: ${reason}`);
          }
        }
        setCriticalIssues(issues);
      })
      .catch(() => {
        setBackendReachable(false);
        setCriticalIssues(["Backend API is not reachable — check that FastAPI is running and the proxy is configured."]);
      });
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;
    setLoading(true);
    try {
      await login(username, password);
      navigate("/dashboard");
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Login failed. Check your credentials.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{
      background: "linear-gradient(135deg, hsl(190 60% 30%) 0%, hsl(195 70% 22%) 30%, hsl(200 60% 18%) 60%, hsl(185 50% 25%) 100%)",
    }}>
      {/* Decorative background shapes */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-20 -right-20 w-96 h-96 rounded-full opacity-10" style={{ background: "radial-gradient(circle, hsl(180 70% 50%), transparent)" }} />
        <div className="absolute -bottom-32 -left-32 w-[500px] h-[500px] rounded-full opacity-5" style={{ background: "radial-gradient(circle, hsl(180 60% 40%), transparent)" }} />
      </div>

      {/* Main card */}
      <div className="relative w-full max-w-[900px] rounded-2xl overflow-hidden shadow-2xl flex min-h-[520px]" style={{ boxShadow: "0 25px 60px -15px rgba(0,0,0,0.5)" }}>
        
        {/* Left Panel — Info */}
        <div className="hidden lg:flex flex-col justify-center flex-1 p-10 text-white relative" style={{
          background: "linear-gradient(180deg, hsl(195 80% 18%) 0%, hsl(200 70% 14%) 100%)",
        }}>
          <div className="flex items-center gap-3 mb-8 bg-white/10 rounded-xl px-4 py-3 w-fit backdrop-blur-sm">
            <img src={mohLogo} alt="Ministry of Health" className="h-10 object-contain" />
          </div>

          <h2 className="text-2xl font-bold mb-3">Welcome to Medisoft Cloud</h2>
          <p className="text-white/70 text-sm mb-6 leading-relaxed">
            Medisoft is an advanced medical software designed for <strong className="text-white/90">efficient patient management, insurance processing, and secure data handling</strong>.
          </p>
          
          <h3 className="text-base font-semibold mb-2">Connected to Cloud Sync</h3>
          <p className="text-white/60 text-sm mb-5 leading-relaxed">
            This system is securely connected to the <strong className="text-white/80">Central Monitoring Server</strong>, enabling seamless <strong className="text-white/80">data exchange and real-time synchronization</strong>.
          </p>

          <h4 className="text-sm font-semibold mb-3">Available Services:</h4>
          <div className="space-y-2">
            {[
              { icon: Database, label: "MySQL Replication Monitoring" },
              { icon: BarChart3, label: "Real-time Analytics & Metrics" },
              { icon: Cloud, label: "Cloud Data Exchange" },
              { icon: Shield, label: "Backup Compliance Monitoring" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-2.5 text-sm text-white/80">
                <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
                <span>{label}</span>
              </div>
            ))}
          </div>

          {/* Dynasoft credit */}
          <div className="mt-8 pt-4 border-t border-white/10 flex items-center gap-2">
            <img src={dynasoftLogo} alt="Dynasoft" className="h-6 object-contain rounded" />
            <span className="text-[10px] text-white/40">Powered by Dynasoft</span>
          </div>
        </div>

        {/* Right Panel — Login form */}
        <div className="flex-1 bg-white flex flex-col items-center justify-center p-10">
          <div className="mb-6 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <img src={medisoftLogo} alt="Medisoft" className="h-12 object-contain" />
            </div>
            <h1 className="text-lg font-bold text-gray-800 mt-2">Medisoft Cloud</h1>
            <p className="text-xs text-gray-400 mt-0.5">Data Sync Management System</p>
          </div>

          <h2 className="text-lg font-bold text-gray-800 mb-6">Login to Your Account</h2>

          {criticalIssues.length > 0 && (
            <div className="w-full max-w-xs mb-4 rounded-md border border-red-300 bg-red-50 p-3">
              <div className="flex items-center gap-2 text-red-700 font-semibold text-xs mb-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                {backendReachable === false ? "Backend offline" : `${criticalIssues.length} critical issue${criticalIssues.length>1?"s":""} detected`}
              </div>
              <ul className="text-[11px] text-red-700/90 space-y-0.5 list-disc pl-4">
                {criticalIssues.slice(0, 5).map((m) => <li key={m}>{m}</li>)}
              </ul>
            </div>
          )}

          <form onSubmit={handleLogin} className="w-full max-w-xs space-y-4">
            <div className="flex items-center border rounded-lg overflow-hidden bg-gray-50">
              <div className="px-3 py-2.5 bg-gray-100 border-r">
                <User className="w-4 h-4 text-gray-400" />
              </div>
              <Input
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 text-gray-700 placeholder:text-gray-400"
              />
            </div>
            <div className="flex items-center border rounded-lg overflow-hidden bg-gray-50">
              <div className="px-3 py-2.5 bg-gray-100 border-r">
                <Lock className="w-4 h-4 text-gray-400" />
              </div>
              <Input
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 text-gray-700 placeholder:text-gray-400"
              />
            </div>
            <Button type="submit" disabled={loading} className="w-full font-semibold text-white h-11" style={{ background: "linear-gradient(135deg, hsl(180 70% 40%), hsl(195 80% 35%))" }}>
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <LogIn className="w-4 h-4 mr-2" />}
              {loading ? "Logging in..." : "Login"}
            </Button>
            <p className="text-center text-xs text-blue-500 hover:underline cursor-pointer mt-3">Forgot Password?</p>
            <p className="text-center text-xs text-gray-400 mt-2">
              For support, call <strong className="text-gray-600">your system administrator</strong>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
