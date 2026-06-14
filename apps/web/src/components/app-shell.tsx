"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { LogOut, LayoutDashboard } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [{ href: "/", label: "Dashboard", icon: LayoutDashboard }];

/** Auth-gated layout: redirects to /login when there is no session. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { session, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (!loading && session === null) router.replace("/login");
  }, [loading, session, router]);

  if (loading || session === null) {
    return <div className="flex h-screen items-center justify-center text-muted-foreground">Loading…</div>;
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col border-r border-border bg-card/40 p-4">
        <div className="px-2 py-3 text-lg font-semibold">
          spin<span className="text-primary">2</span>note
        </div>
        <nav className="mt-4 flex flex-1 flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                pathname === href ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto border-t border-border pt-3">
          <div className="truncate px-3 pb-2 text-xs text-muted-foreground">{session.user?.email}</div>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => signOut()}>
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </div>
      </aside>
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}
