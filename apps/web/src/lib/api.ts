import type { components } from "./api/schema";

// Types come straight from the backend OpenAPI spec (regenerate via `npm run generate-client`).
export type Overview = components["schemas"]["Overview"];
export type StackBucket = components["schemas"]["StackBucket"];
export type RecentHand = components["schemas"]["RecentHand"];
export type UploadResult = components["schemas"]["UploadResult"];

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export function getOverview(token: string, format?: "3max" | "6max"): Promise<Overview> {
  const qs = format ? `?format=${format}` : "";
  return apiFetch<Overview>(`/stats/overview${qs}`, token);
}

export function getRecentHands(token: string, limit = 50): Promise<RecentHand[]> {
  return apiFetch<RecentHand[]>(`/hands/recent?limit=${limit}`, token);
}

export function uploadFile(token: string, file: File): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<UploadResult>("/ingest/upload", token, { method: "POST", body });
}
