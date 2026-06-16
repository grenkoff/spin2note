import type { components } from "./api/schema";

// Types come straight from the backend OpenAPI spec (regenerate via `npm run generate-client`).
export type Overview = components["schemas"]["Overview"];
export type StackBucket = components["schemas"]["StackBucket"];
export type TimelinePoint = components["schemas"]["TimelinePoint"];
export type RecentHand = components["schemas"]["RecentHand"];
export type UploadResult = components["schemas"]["UploadResult"];
export type ImportSummary = components["schemas"]["ImportSummary"];

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

/** Upload a gzipped bundle of concatenated files; returns the compressed byte count. */
export async function uploadBulk(
  token: string,
  gzipped: Uint8Array,
  sessionId: string,
): Promise<number> {
  const res = await fetch(`${API_URL}/ingest/bulk`, {
    method: "POST",
    // Uint8Array is a valid fetch body at runtime; cast around TS 5.7 typed-array generics.
    body: gzipped as unknown as BodyInit,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/octet-stream",
      "X-Bundle-Gzip": "1",
      "X-Upload-Session": sessionId,
    },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return gzipped.byteLength;
}

/**
 * Upload one archive (zip/rar/7z/…) for server-side extraction; returns its byte count.
 * Uses XHR so the caller can track real upload progress via `onUploadProgress(loadedBytes)` —
 * fetch() does not expose request-body upload progress.
 */
export function uploadArchive(
  token: string,
  file: File,
  sessionId: string,
  onUploadProgress?: (loaded: number) => void,
): Promise<number> {
  return new Promise<number>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/ingest/archive`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-Upload-Session", sessionId);
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    if (onUploadProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onUploadProgress(e.loaded);
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(file.size);
      else reject(new Error(`API ${xhr.status}: ${xhr.responseText}`));
    };
    xhr.onerror = () => reject(new Error("Network error during archive upload"));
    xhr.send(file);
  });
}

/** Aggregated added/skipped report for one upload session. */
export function getImportSummary(token: string, sessionId: string): Promise<ImportSummary> {
  return apiFetch<ImportSummary>(`/imports/${sessionId}`, token);
}
