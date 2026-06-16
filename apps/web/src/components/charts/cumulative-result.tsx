"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TimelinePoint } from "@/lib/api";

/**
 * Cumulative "winnings graph" (PokerTracker/HM style): X is the sequential hand/tournament index,
 * Y is the running net total. `format` renders the Y value (chips or USD) in ticks and tooltip.
 */
export function CumulativeResult({
  data,
  format,
}: {
  data: TimelinePoint[];
  format: (value: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <defs>
          <linearGradient id="cumFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(152 70% 45%)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="hsl(152 70% 45%)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 17%)" vertical={false} />
        <XAxis dataKey="idx" tick={{ fill: "hsl(215 20% 65%)", fontSize: 12 }} />
        <YAxis
          tick={{ fill: "hsl(215 20% 65%)", fontSize: 12 }}
          tickFormatter={(v) => format(Number(v))}
          width={72}
        />
        <ReferenceLine y={0} stroke="hsl(217 33% 30%)" />
        <Tooltip
          contentStyle={{
            background: "hsl(222 40% 8%)",
            border: "1px solid hsl(217 33% 17%)",
            borderRadius: 8,
            color: "hsl(210 40% 96%)",
          }}
          formatter={(value: number) => [format(Number(value)), "Cumulative"]}
          labelFormatter={(idx) => `#${idx}`}
        />
        <Area
          type="monotone"
          dataKey="cumulative"
          stroke="hsl(152 70% 45%)"
          strokeWidth={2}
          fill="url(#cumFill)"
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
