"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatChips, formatPer100 } from "@/lib/utils";

export type CategoryRow = {
  label: string;
  perHundredChips: number;
  perHundredEv: number;
  totalChips: number;
  totalEv: number;
  hands: number;
  winrate: number;
};

const CHIPS = "hsl(152 70% 45%)";
const EV = "hsl(210 90% 60%)";

function CategoryTooltip({ active, payload }: { active?: boolean; payload?: { payload: CategoryRow }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-md border border-border bg-[hsl(222_40%_8%)] px-3 py-2 text-xs text-foreground">
      <div className="mb-1 font-semibold">{r.label}</div>
      <div>chips/100: <span style={{ color: CHIPS }}>{formatPer100(r.perHundredChips)}</span></div>
      <div>chipEV/100: <span style={{ color: EV }}>{formatPer100(r.perHundredEv)}</span></div>
      <div className="mt-1 text-muted-foreground">
        total {formatChips(r.totalChips)} · EV {formatChips(r.totalEv)}
      </div>
      <div className="text-muted-foreground">{r.hands.toLocaleString("en-US")} hands · {(r.winrate * 100).toFixed(1)}% won</div>
    </div>
  );
}

/** Grouped bars per category (position or stack): chips/100 vs chipEV/100. */
export function MetricByCategory({ data }: { data: CategoryRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 17%)" vertical={false} />
        <XAxis dataKey="label" tick={{ fill: "hsl(215 20% 65%)", fontSize: 12 }} />
        <YAxis tick={{ fill: "hsl(215 20% 65%)", fontSize: 12 }} width={56} />
        <ReferenceLine y={0} stroke="hsl(217 33% 30%)" />
        <Tooltip cursor={{ fill: "hsl(217 33% 17% / 0.4)" }} content={<CategoryTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar name="chips/100" dataKey="perHundredChips" fill={CHIPS} radius={[3, 3, 0, 0]} />
        <Bar name="chipEV/100" dataKey="perHundredEv" fill={EV} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
