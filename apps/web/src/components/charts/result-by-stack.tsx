"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { StackBucket } from "@/lib/api";

export function ResultByStack({ data }: { data: StackBucket[] }) {
  const rows = data.map((d) => ({ bb: `${d.effective_stack_bb}bb`, result: d.result }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 17%)" vertical={false} />
        <XAxis dataKey="bb" tick={{ fill: "hsl(215 20% 65%)", fontSize: 12 }} />
        <YAxis tick={{ fill: "hsl(215 20% 65%)", fontSize: 12 }} />
        <Tooltip
          contentStyle={{
            background: "hsl(222 40% 8%)",
            border: "1px solid hsl(217 33% 17%)",
            borderRadius: 8,
            color: "hsl(210 40% 96%)",
          }}
        />
        <Bar dataKey="result" radius={[4, 4, 0, 0]}>
          {rows.map((r, i) => (
            <Cell key={i} fill={r.result >= 0 ? "hsl(152 70% 45%)" : "hsl(0 72% 51%)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
