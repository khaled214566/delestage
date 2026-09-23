/**
 * AuthContext — global authentication state.
 *
 * Provides:
 *   - user: decoded JWT claims (role, scope, name…) or null when logged out
 *   - login(username, password): calls POST /auth/login, stores token, sets user
 *   - logout(): clears token and user
 *   - isLoading: true while the token is being validated on first mount
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import apiClient from '../api/client';

// ─── Types ────────────────────────────────────────────────────────────────────

export type UserRole =
  | 'DISPATCHER'
  | 'CRC_OPERATOR'
  | 'BCC_OPERATOR'
  | 'ADMIN';

export interface AuthUser {
  id: number;
  username: string;
  name: string;
  role: UserRole;
  scope_type: string;
  scope_id: string | null;
  is_active: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ─── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On first mount, validate any stored token by fetching /auth/me
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setIsLoading(false);
      return;
    }
    apiClient
      .get<AuthUser>('/auth/me')
      .then(({ data }) => setUser(data))
      .catch(() => localStorage.removeItem('access_token'))
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    // FastAPI OAuth2 password flow expects application/x-www-form-urlencoded
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);

    const { data } = await apiClient.post<{ access_token: string }>(
      '/auth/login',
      form,
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    );

    localStorage.setItem('access_token', data.access_token);

    // Fetch the full user profile
    const { data: profile } = await apiClient.get<AuthUser>('/auth/me');
    setUser(profile);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
