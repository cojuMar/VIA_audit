import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type UserRole = 'super_admin' | 'admin' | 'end_user';

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  tenant_id: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  error: string | null;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  login: async () => {},
  logout: () => {},
  error: null,
});

const TOKEN_KEY = 'via-auth-token';
const USER_KEY  = 'via-auth-user';

function loadStored(): { user: AuthUser | null; token: string | null } {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const raw   = localStorage.getItem(USER_KEY);
    if (token && raw) {
      const user = JSON.parse(raw) as AuthUser;
      return { user, token };
    }
  } catch { /* ignore */ }
  return { user: null, token: null };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const stored = loadStored();
  const [user,      setUser]      = useState<AuthUser | null>(stored.user);
  const [token,     setToken]     = useState<string | null>(stored.token);
  const [isLoading, setIsLoading] = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || 'Invalid email or password');
      }
      const data = await res.json();
      const authUser: AuthUser = data.user;
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(USER_KEY,  JSON.stringify(authUser));
      setToken(data.access_token);
      setUser(authUser);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setUser(null);
    setToken(null);
    setError(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      user,
      token,
      isAuthenticated: !!user,
      isLoading,
      login,
      logout,
      error,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
