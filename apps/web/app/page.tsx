"use client";

import * as React from "react";

import { CumulativeResult } from "@/components/charts/cumulative-result";
import { MetricByCategory, type CategoryRow } from "@/components/charts/metric-by-category";
import { AppShell } from "@/components/app-shell";
import { Uploader } from "@/components/uploader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import {
  getOverview,
  getRecentHands,
  type Overview,
  type PositionBucket,
  type RecentHand,
  type StackBucket,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatChips, formatUsd } from "@/lib/utils";

type Format = "3max" | "6max" | undefined;

// Canonical poker order (BTN shown for "BU"); positions absent in 3-max simply don't appear.
const POSITION_ORDER = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];

function toRow(label: string, b: { hands: number; result: number; result_ev: number; winrate: number }): CategoryRow {
  const per = (v: number) => (b.hands > 0 ? (v / b.hands) * 100 : 0);
  return {
    label,
    perHundredChips: per(b.result),
    perHundredEv: per(b.result_ev),
    totalChips: b.result,
    totalEv: b.result_ev,
    hands: b.hands,
    winrate: b.winrate,
  };
}

function positionRows(by: PositionBucket[]): CategoryRow[] {
  const idx = (p: string) => {
    const i = POSITION_ORDER.indexOf(p);
    return i === -1 ? POSITION_ORDER.length : i;
  };
  return [...by].sort((a, b) => idx(a.position) - idx(b.position)).map((b) => toRow(b.position, b));
}

function stackRows(by: StackBucket[]): CategoryRow[] {
  return by.map((b) => toRow(`${b.effective_stack_bb}bb`, b));
}

function Stat({ title, value }: { title: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <div className="text-2xl font-semibold text-foreground">{value}</div>
      </CardHeader>
    </Card>
  );
}

export default function DashboardPage() {
  return (
    <AppShell>
      <Dashboard />
    </AppShell>
  );
}

function Dashboard() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";
  const [format, setFormat] = React.useState<Format>(undefined);
  const [overview, setOverview] = React.useState<Overview | null>(null);
  const [hands, setHands] = React.useState<RecentHand[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    if (!token) return;
    setError(null);
    Promise.all([getOverview(token, format), getRecentHands(token, 25)])
      .then(([o, h]) => {
        setOverview(o);
        setHands(h);
      })
      .catch((e) => setError(String(e)));
  }, [token, format]);

  React.useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <div className="flex gap-2">
          {([undefined, "3max", "6max"] as Format[]).map((f) => (
            <Button
              key={f ?? "all"}
              variant={format === f ? "default" : "outline"}
              size="sm"
              onClick={() => setFormat(f)}
            >
              {f ?? "All"}
            </Button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Uploader onComplete={load} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat title="Hands" value={(overview?.total_hands ?? 0).toLocaleString("en-US")} />
        <Stat title="Tournaments" value={(overview?.total_tournaments ?? 0).toLocaleString("en-US")} />
        <Stat title="Avg multiplier" value={`${overview?.avg_multiplier ?? 0}x`} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>By position — chips/100 vs chipEV/100</CardTitle>
          <p className="text-xs text-muted-foreground">Where you earn most/least by seat (BU = BTN). chipEV strips all-in variance.</p>
        </CardHeader>
        <CardContent>
          {overview && overview.by_position.length > 0 ? (
            <MetricByCategory data={positionRows(overview.by_position)} />
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">No hands yet — upload a hand history.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>By effective stack — chips/100 vs chipEV/100</CardTitle>
          <p className="text-xs text-muted-foreground">Where you earn most/least by tournament stage (stack depth in BB).</p>
        </CardHeader>
        <CardContent>
          {overview && overview.by_stack.length > 0 ? (
            <MetricByCategory data={stackRows(overview.by_stack)} />
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">No hands yet — upload a hand history.</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Net result over time (chips)</CardTitle>
          </CardHeader>
          <CardContent>
            {overview && overview.chips_timeline.length > 0 ? (
              <CumulativeResult data={overview.chips_timeline} format={formatChips} />
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">No hands yet — upload a hand history.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Net result over time ($)</CardTitle>
            <p className="text-xs text-muted-foreground">Real-money P&amp;L across all formats.</p>
          </CardHeader>
          <CardContent>
            {overview && overview.dollars_timeline.length > 0 ? (
              <CumulativeResult data={overview.dollars_timeline} format={formatUsd} />
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">No tournament summaries yet — upload one.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent hands</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>Time</TH>
                <TH>Format</TH>
                <TH>Eff. stack</TH>
                <TH>Position</TH>
                <TH>Board</TH>
                <TH className="text-right">Result</TH>
              </TR>
            </THead>
            <TBody>
              {hands.map((h) => (
                <TR key={h.source_hand_id}>
                  <TD className="text-muted-foreground">{h.played_at.replace("T", " ").slice(0, 19)}</TD>
                  <TD>{h.tournament_format}</TD>
                  <TD>{h.effective_stack_bb}bb</TD>
                  <TD>{h.position}</TD>
                  <TD className="font-mono text-xs">{h.board || "—"}</TD>
                  <TD className="text-right">
                    <Badge variant={h.result >= 0 ? "positive" : "negative"}>{formatChips(h.result)}</Badge>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
