"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { getMe } from "@/lib/api";
import type { User } from "@/lib/types";

export interface Auth {
  /** Undefined until the backend has answered; null when nobody is logged in. */
  user: User | null | undefined;
  setUser: (user: User | null) => void;
}

const AuthContext = createContext<Auth | null>(null);

/** Who is logged in. The session cookie is HttpOnly, so only GET /auth/me can tell. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    getMe()
      .catch(() => null) // an unreachable backend reads as logged out; pages report it
      .then((me) => {
        if (!cancelled) setUser(me);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const auth = useMemo(() => ({ user, setUser }), [user]);
  return <AuthContext value={auth}>{children}</AuthContext>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth needs an <AuthProvider>");
  return auth;
}
