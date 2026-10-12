"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { fetchMe, signIn, signUp, type Session } from "@/lib/api";

/**
 * Session state for the whole app.
 *
 * `isAdmin` here decides whether the Reviews link renders and whether the
 * Reviews page shows its contents. That is presentation, not protection: the
 * data itself is guarded by the check inside /api/reviews, which runs
 * server-side on every request and does not trust anything this file says.
 *
 * The admin address is never present in this bundle. The server computes
 * `is_admin` from the signed-in email and sends back only the boolean.
 */
const TOKEN_STORAGE = "glyph-session";

interface AuthState {
  email: string | null;
  isAdmin: boolean;
  token: string | null;
  /** True until the stored token has been re-checked against the server. */
  loading: boolean;
  logIn: (email: string, password: string) => Promise<Session>;
  register: (email: string, password: string) => Promise<Session>;
  logOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE);
  } catch {
    // Private windows and blocked site data both throw here.
    return null;
  }
}

function writeStoredToken(token: string | null): void {
  try {
    if (token === null) window.localStorage.removeItem(TOKEN_STORAGE);
    else window.localStorage.setItem(TOKEN_STORAGE, token);
  } catch {
    // Not being able to persist is survivable - the session lasts the page.
  }
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  // A stored token is not trusted on its face: it may be expired, revoked by a
  // secret rotation, or for an email that is no longer the owner. The server
  // re-derives both facts on every load.
  useEffect(() => {
    const stored = readStoredToken();
    if (!stored) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    fetchMe(stored, controller.signal)
      .then((me) => {
        setToken(stored);
        setEmail(me.email);
        setIsAdmin(me.is_admin);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        // Expired or rejected: drop it rather than leaving a dead token around.
        writeStoredToken(null);
        setToken(null);
        setEmail(null);
        setIsAdmin(false);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const adopt = useCallback((session: Session) => {
    writeStoredToken(session.token);
    setToken(session.token);
    setEmail(session.email);
    setIsAdmin(session.is_admin);
    return session;
  }, []);

  const logIn = useCallback(
    async (e: string, password: string) => adopt(await signIn(e, password)),
    [adopt],
  );

  const register = useCallback(
    async (e: string, password: string) => adopt(await signUp(e, password)),
    [adopt],
  );

  const logOut = useCallback(() => {
    writeStoredToken(null);
    setToken(null);
    setEmail(null);
    setIsAdmin(false);
  }, []);

  const value = useMemo(
    () => ({ email, isAdmin, token, loading, logIn, register, logOut }),
    [email, isAdmin, token, loading, logIn, register, logOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
