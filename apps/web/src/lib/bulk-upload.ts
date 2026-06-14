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
  bytesUploaded: number; // original bytes sent so far (drives the progress bar)
  bytesTotal: number; // sum of selected file sizes, known upfront
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
    bytesTotal: files.reduce((s, f) => s + f.size, 0),
  };

  // Run a text-bundle upload under backpressure (at most CONCURRENCY in flight). `bytes` is the
  // original (uncompressed) size of the bundle, credited to the bar once the chunk lands.
  const run = (bytes: number, taskFn: () => Promise<unknown>) => {
    p.chunksStarted += 1;
    onProgress({ ...p });
    const task = (async () => {
      await sem.acquire();
      try {
        await taskFn();
        p.chunksUploaded += 1;
        p.bytesUploaded += bytes;
        onProgress({ ...p });
      } finally {
        sem.release();
      }
    })();
    inFlight.push(task);
  };

  const ship = async (text: string, bytes: number) =>
    run(bytes, async () => uploadBulk(token, await gzipAsync(encoder.encode(text)), sessionId));

  // Stream one archive to the server, crediting the bar from real upload progress (XHR).
  const shipArchive = (a: File) => {
    p.chunksStarted += 1;
    onProgress({ ...p });
    const task = (async () => {
      await sem.acquire();
      try {
        let last = 0;
        await uploadArchive(token, a, sessionId, (loaded) => {
          p.bytesUploaded += loaded - last;
          last = loaded;
          onProgress({ ...p });
        });
        p.bytesUploaded += a.size - last; // settle any rounding from the last progress event
        p.filesRead += 1;
        p.chunksUploaded += 1;
        onProgress({ ...p });
      } finally {
        sem.release();
      }
    })();
    inFlight.push(task);
  };

  let hh: string[] = [];
  let hhSize = 0;
  let hhBytes = 0;
  let sm: string[] = [];
  let smSize = 0;
  let smBytes = 0;

  // Read files with bounded concurrency (disk I/O parallelism) while bundling sequentially.
  const READ_CONCURRENCY = 16;
  for (let i = 0; i < files.length; i += READ_CONCURRENCY) {
    const batch = files.slice(i, i + READ_CONCURRENCY);
    // Archives go straight to the server (extracted there); the rest are read as text.
    for (const a of batch.filter((f) => isArchive(f.name))) shipArchive(a);
    const textFiles = batch.filter((f) => !isArchive(f.name));
    const texts = await Promise.all(textFiles.map((f) => f.text()));
    for (let j = 0; j < textFiles.length; j++) {
      const text = texts[j];
      const fileBytes = textFiles[j].size;
      p.filesRead += 1;
      const kind = classify(text);
      if (kind === "hh") {
        hh.push(text);
        hhSize += text.length;
        hhBytes += fileBytes;
        if (hhSize >= CHUNK_BYTES) {
          await ship(hh.join("\n"), hhBytes);
          hh = [];
          hhSize = 0;
          hhBytes = 0;
        }
      } else if (kind === "summary") {
        sm.push(text);
        smSize += text.length;
        smBytes += fileBytes;
        if (smSize >= CHUNK_BYTES) {
          await ship(sm.join("\n"), smBytes);
          sm = [];
          smSize = 0;
          smBytes = 0;
        }
      } else {
        p.filesSkipped += 1;
      }
    }
    onProgress({ ...p });
  }

  if (hh.length) await ship(hh.join("\n"), hhBytes);
  if (sm.length) await ship(sm.join("\n"), smBytes);
  await Promise.all(inFlight);
  p.bytesUploaded = p.bytesTotal; // settle the bar to 100% (skipped files never shipped bytes)
  onProgress({ ...p });
  return { sessionId, progress: p };
}
