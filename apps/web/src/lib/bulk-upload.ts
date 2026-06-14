import { gzip } from "fflate";

import { uploadArchive, uploadBulk } from "./api";

// Archives are extracted server-side (one engine for zip/rar/7z/tar/…); plain .txt files are
// bundled client-side.
const ARCHIVE_RE = /\.(zip|rar|7z|tar|tar\.gz|tgz|gz|bz2|xz)$/i;
export function isArchive(name: string): boolean {
  return ARCHIVE_RE.test(name);
}

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

  // Run an upload task under backpressure (at most CONCURRENCY in flight).
  const run = (taskFn: () => Promise<number>) => {
    p.chunksStarted += 1;
    onProgress({ ...p });
    const task = (async () => {
      await sem.acquire();
      try {
        const n = await taskFn();
        p.chunksUploaded += 1;
        p.bytesUploaded += n;
        onProgress({ ...p });
      } finally {
        sem.release();
      }
    })();
    inFlight.push(task);
  };

  const ship = async (text: string) =>
    run(async () => uploadBulk(token, await gzipAsync(encoder.encode(text)), sessionId));

  let hh: string[] = [];
  let hhSize = 0;
  let sm: string[] = [];
  let smSize = 0;

  // Read files with bounded concurrency (disk I/O parallelism) while bundling sequentially.
  const READ_CONCURRENCY = 16;
  for (let i = 0; i < files.length; i += READ_CONCURRENCY) {
    const batch = files.slice(i, i + READ_CONCURRENCY);
    // Archives go straight to the server (extracted there); the rest are read as text.
    const archives = batch.filter((f) => isArchive(f.name));
    for (const a of archives) {
      p.filesRead += 1;
      run(() => uploadArchive(token, a, sessionId));
    }
    const textFiles = batch.filter((f) => !isArchive(f.name));
    const texts = await Promise.all(textFiles.map((f) => f.text()));
    for (const text of texts) {
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
    }
    onProgress({ ...p });
  }

  if (hh.length) await ship(hh.join("\n"));
  if (sm.length) await ship(sm.join("\n"));
  await Promise.all(inFlight);
  onProgress({ ...p });
  return { sessionId, progress: p };
}
