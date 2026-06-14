import { gzip } from "fflate";

import { uploadBulk } from "./api";

// The browser concatenates many small files into ~16 MB chunks and gzips them, so a base of
// hundreds of thousands of files becomes a few dozen requests. The backend parsers split by
// record markers, so concatenation is lossless.
const CHUNK_BYTES = 16 * 1024 * 1024;
const CONCURRENCY = 6;

export interface BulkProgress {
  filesTotal: number;
  filesRead: number;
  filesSkipped: number;
  chunksUploaded: number;
  chunksStarted: number;
  bytesUploaded: number;
}

function gzipAsync(data: Uint8Array): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    gzip(data, { level: 1 }, (err, out) => (err ? reject(err) : resolve(out)));
  });
}

/** Minimal counting semaphore for upload backpressure. */
class Semaphore {
  private count: number;
  private waiters: (() => void)[] = [];
  constructor(n: number) {
    this.count = n;
  }
  async acquire(): Promise<void> {
    if (this.count > 0) {
      this.count -= 1;
      return;
    }
    await new Promise<void>((r) => this.waiters.push(r));
  }
  release(): void {
    this.count += 1;
    this.waiters.shift()?.();
  }
}

function classify(text: string): "hh" | "summary" | null {
  if (text.includes("Poker Hand #")) return "hh";
  if (text.includes("Buy-in:") || text.startsWith("Tournament #")) return "summary";
  return null;
}

export async function bulkUpload(
  files: File[],
  token: string,
  onProgress: (p: BulkProgress) => void,
): Promise<{ sessionId: string; progress: BulkProgress }> {
  const sessionId = crypto.randomUUID(); // groups all chunks of this upload for the report
  const encoder = new TextEncoder();
  const sem = new Semaphore(CONCURRENCY);
  const inFlight: Promise<void>[] = [];
  const p: BulkProgress = {
    filesTotal: files.length,
    filesRead: 0,
    filesSkipped: 0,
    chunksUploaded: 0,
    chunksStarted: 0,
    bytesUploaded: 0,
  };

  const ship = async (text: string) => {
    p.chunksStarted += 1;
    onProgress({ ...p });
    await sem.acquire(); // backpressure: at most CONCURRENCY chunks in flight
    const task = (async () => {
      try {
        const gz = await gzipAsync(encoder.encode(text));
        const n = await uploadBulk(token, gz, sessionId);
        p.chunksUploaded += 1;
        p.bytesUploaded += n;
        onProgress({ ...p });
      } finally {
        sem.release();
      }
    })();
    inFlight.push(task);
  };

  let hh: string[] = [];
  let hhSize = 0;
  let sm: string[] = [];
  let smSize = 0;

  for (const file of files) {
    const text = await file.text();
    p.filesRead += 1;
    const kind = classify(text);
    if (kind === "hh") {
      hh.push(text);
      hhSize += text.length;
      if (hhSize >= CHUNK_BYTES) {
        await ship(hh.join("\n"));
        hh = [];
        hhSize = 0;
      }
    } else if (kind === "summary") {
      sm.push(text);
      smSize += text.length;
      if (smSize >= CHUNK_BYTES) {
        await ship(sm.join("\n"));
        sm = [];
        smSize = 0;
      }
    } else {
      p.filesSkipped += 1;
    }
    if (p.filesRead % 250 === 0) onProgress({ ...p });
  }

  if (hh.length) await ship(hh.join("\n"));
  if (sm.length) await ship(sm.join("\n"));
  await Promise.all(inFlight);
  onProgress({ ...p });
  return { sessionId, progress: p };
}
