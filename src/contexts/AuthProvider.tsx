import { createContext, useState, ReactNode } from "react";
import { loginUser } from "@/lib/api";
import { DEV_TOKEN, DEV_USER, isDevCredentials } from "@/lib/auth-config";

export interface AuthUser {
  id: string;
  username: string;
  role: "admin" | "user";
}

export interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = localStorage.getItem("auth_user");
    return stored ? JSON.parse(stored) : null;
  });

  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem("auth_token")
  );

  const persist = (accessToken: string, userData: AuthUser) => {
    localStorage.setItem("auth_token", accessToken);
    localStorage.setItem("auth_user", JSON.stringify(userData));
    setToken(accessToken);
    setUser(userData);
  };

  const login = async (username: string, password: string) => {
    // 1. Dev bypass (works even if backend is unreachable)
    if (isDevCredentials(username, password)) {
      persist(DEV_TOKEN, DEV_USER);
      return;
    }

    // 2. Real backend login
    try {
      const res = await loginUser(username, password);
      const { access_token, user: userData } = res.data;
      persist(access_token, userData);
    } catch (err) {
      // 3. If backend down AND dev creds — already handled above.
      throw err;
    }
  };

  const logout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
