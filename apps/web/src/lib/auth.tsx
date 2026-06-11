"use client";

import { GoTrueClient, type Session } from "@supabase/auth-js";
import * as React from "react";

// Self-hosted Supabase Auth (GoTrue). Presentation-only: the frontend just authenticates and
// forwards the JWT to FastAPI, which enforces everything server-side.
const GOTRUE_URL = process.env.NEXT_PUBLIC_GOTRUE_URL ?? "http://localhost:9999";

let _client: GoTrueClient | null = null;

function getClient(): GoTrueClient {
  if (_client === null) {
    _client = new GoTrueClient({
      url: GOTRUE_URL,
      storageKey: "spin2note-auth",
      autoRefreshToken: true,
      persistSession: true,
    });
  }
  return _client;
}

interface AuthState {
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<string | null>;
  signUp: (email: string, password: string) => Promise<string | null>;
  signOut: () => Promise<void>;
}

const AuthContext = React.createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = React.useState<Session | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    const client = getClient();
    client.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = client.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);

  const signIn = React.useCallback(async (email: string, password: string) => {
    const { error } = await getClient().signInWithPassword({ email, password });
    return error ? error.message : null;
  }, []);

  const signUp = React.useCallback(async (email: string, password: string) => {
    const { error } = await getClient().signUp({ email, password });
    return error ? error.message : null;
  }, []);

  const signOut = React.useCallback(async () => {
    await getClient().signOut();
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = React.useContext(AuthContext);
  if (ctx === null) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
