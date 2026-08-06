/** Authentication context: session state, login, registration and logout. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { setUnauthorizedHandler, tokenStore } from '@/api/client';
import { authApi } from '@/api/resources';
import type { User } from '@/types';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  /** True until the initial session rehydration completes. */
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, fullName: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  // A refresh that fails anywhere in the app ends the session here.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
  }, []);

  // Rehydrate the session on mount from the persisted token.
  useEffect(() => {
    const controller = new AbortController();

    async function rehydrate() {
      if (!tokenStore.access) {
        setIsLoading(false);
        return;
      }
      try {
        setUser(await authApi.me(controller.signal));
      } catch {
        // An invalid or expired token is not an error worth surfacing on
        // first load — it just means the visitor needs to sign in.
        tokenStore.clear();
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    }

    void rehydrate();
    return () => controller.abort();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    tokenStore.set(result.tokens.access_token, result.tokens.refresh_token);
    setUser(result.user);
  }, []);

  const register = useCallback(
    async (email: string, fullName: string, password: string) => {
      const result = await authApi.register(email, fullName, password);
      tokenStore.set(result.tokens.access_token, result.tokens.refresh_token);
      setUser(result.user);
    },
    [],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: user !== null,
      isLoading,
      login,
      register,
      logout,
      updateUser: setUser,
    }),
    [user, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider.');
  }
  return context;
}
