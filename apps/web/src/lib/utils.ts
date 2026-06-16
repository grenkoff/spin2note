import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatChips(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-US")}`;
}

export function formatUsd(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${sign}$${abs}`;
}

/** Chips per 100 hands, rounded — the comparable winrate metric for the per-spot bars. */
export function formatPer100(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString("en-US")}`;
}
