"use client";

import * as React from "react";
import { FolderUp, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getImportSummary, type ImportSummary } from "@/lib/api";
import { bulkUpload, isArchive, type BulkProgress } from "@/lib/bulk-upload";
import { useAuth } from "@/lib/auth";

const ARCHIVE_ACCEPT = ".zip,.rar,.7z,.tar,.gz,.tgz,.bz2,.xz";

// readEntries yields a directory in batches; keep calling until it returns an empty batch.
async function readAllEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  const out: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
    if (batch.length === 0) break;
    out.push(...batch);
  }
  return out;
}

// Resolve file entries in bounded batches: firing thousands of FileSystemFileEntry.file() calls at
// once (a folder of 10k+ files) overwhelms Chromium and the whole drop silently fails.
const FILE_RESOLVE_BATCH = 64;

// Collect dropped folders and archives only — loose individual files are intentionally ignored
// (uploading is folder- or archive-based). Folder entries are walked breadth-first with bounded
// concurrency; an archive is taken via getAsFile(). We decide archive-vs-file from entry.name
// (sync, no file resolution) so dropping a huge loose-file selection never touches the files.
// `onCount` reports progress on large folder drops.
async function filesFromDrop(dt: DataTransfer, onCount?: (n: number) => void): Promise<File[]> {
  const items = Array.from(dt.items).filter((i) => i.kind === "file");
  // Snapshot the entries synchronously (they must be read before the event yields).
  const pairs = items.map((item) => ({ item, entry: item.webkitGetAsEntry?.() ?? null }));

  // Browser without the entry API: keep only archives from the flat list.
  if (pairs.every((p) => p.entry == null)) {
    const archives = Array.from(dt.files).filter((f) => isArchive(f.name));
    onCount?.(archives.length);
    return archives;
  }

  const files: File[] = [];
  const dirQueue: FileSystemDirectoryEntry[] = [];
  for (const p of pairs) {
    if (p.entry?.isDirectory) {
      dirQueue.push(p.entry as FileSystemDirectoryEntry);
    } else if (p.entry && isArchive(p.entry.name)) {
      const f = p.item.getAsFile(); // archive — grab it now, while the item is valid
      if (f) files.push(f);
    }
    // loose non-archive files are ignored
  }
  onCount?.(files.length);

  while (dirQueue.length > 0) {
    const children = await readAllEntries(dirQueue.shift()!.createReader());
    const fileEntries: FileSystemFileEntry[] = [];
    for (const c of children) {
      if (c.isDirectory) dirQueue.push(c as FileSystemDirectoryEntry);
      else fileEntries.push(c as FileSystemFileEntry);
    }
    for (let i = 0; i < fileEntries.length; i += FILE_RESOLVE_BATCH) {
      const slice = fileEntries.slice(i, i + FILE_RESOLVE_BATCH);
      const got = await Promise.all(
        slice.map((fe) => new Promise<File>((res, rej) => fe.file(res, rej))),
      );
      files.push(...got);
      onCount?.(files.length);
    }
  }
  return files;
}

/** Folder / files / archive upload (button or drag-and-drop) with live import report. */
export function Uploader({ onComplete }: { onComplete?: () => void }) {
  const { session } = useAuth();
  const token = session?.access_token ?? "";
  const folderRef = React.useRef<HTMLInputElement>(null);
  const filesRef = React.useRef<HTMLInputElement>(null);
  const [files, setFiles] = React.useState<File[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState<BulkProgress | null>(null);
  const [report, setReport] = React.useState<ImportSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [scanCount, setScanCount] = React.useState<number | null>(null); // reading a dropped folder
  const dragDepth = React.useRef(0); // ignore dragleave from child elements (enter/leave flicker)

  function pickFiles(list: File[]) {
    setFiles(list.filter((f) => f.name.endsWith(".txt") || isArchive(f.name)));
    setReport(null);
    setProgress(null);
    setError(null);
  }

  function pick(list: FileList | null) {
    if (list) pickFiles(Array.from(list));
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    dragDepth.current = 0;
    setDragOver(false);
    if (busy) return;
    setScanCount(0);
    try {
      pickFiles(await filesFromDrop(e.dataTransfer, setScanCount));
    } catch (err) {
      setError(`Could not read the dropped items: ${String(err)}`);
    } finally {
      setScanCount(null);
    }
  }

  function onDragEnter(e: React.DragEvent) {
    e.preventDefault();
    dragDepth.current += 1;
    if (!busy) setDragOver(true);
  }

  function onDragLeave() {
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) setDragOver(false);
  }

  async function start() {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const { sessionId } = await bulkUpload(files, token, setProgress);
      for (let i = 0; i < 1200; i++) {
        const s = await getImportSummary(token, sessionId);
        setReport(s);
        if (s.complete) break;
        await new Promise((r) => setTimeout(r, 1500));
      }
      setFiles([]); // consumed — require a fresh selection before Upload is enabled again
      onComplete?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const pct =
    progress && progress.bytesTotal > 0
      ? Math.min(100, Math.round((progress.bytesUploaded / progress.bytesTotal) * 100))
      : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload hand history — a folder or an archive (.zip/.rar/.7z/…)</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
            dragOver ? "border-primary bg-primary/5" : "border-border"
          }`}
        >
          <UploadCloud className="h-7 w-7 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Drag &amp; drop a folder or an archive (.zip/.rar/.7z/…) here — or
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Button
              variant="outline"
              onClick={() => folderRef.current?.click()}
              disabled={busy || scanCount !== null}
            >
              <FolderUp className="h-4 w-4" /> Choose folder
            </Button>
            <Button
              variant="outline"
              onClick={() => filesRef.current?.click()}
              disabled={busy || scanCount !== null}
            >
              <UploadCloud className="h-4 w-4" /> Choose archive
            </Button>
            <Button onClick={start} disabled={busy || scanCount !== null || files.length === 0}>
              {busy ? "Uploading…" : "Upload"}
            </Button>
          </div>
          {scanCount !== null ? (
            <p className="text-xs text-muted-foreground">
              Reading {scanCount.toLocaleString("en-US")} files…
            </p>
          ) : (
            files.length > 0 &&
            !busy && (
              <p className="text-xs text-muted-foreground">
                {files.length.toLocaleString("en-US")} file{files.length === 1 ? "" : "s"} ready to upload
              </p>
            )
          )}
          <input
            ref={folderRef}
            type="file"
            webkitdirectory=""
            directory=""
            multiple
            className="hidden"
            onChange={(e) => pick(e.target.files)}
          />
          <input
            ref={filesRef}
            type="file"
            multiple
            accept={ARCHIVE_ACCEPT}
            className="hidden"
            onChange={(e) => pick(e.target.files)}
          />
        </div>

        {progress && (
          <div className="flex flex-col gap-2">
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
              <span>Read: {progress.filesRead.toLocaleString("en-US")} / {progress.filesTotal.toLocaleString("en-US")}</span>
              <span>Uploads: {progress.chunksUploaded} / {progress.chunksStarted}</span>
              <span>Sent: {(progress.bytesUploaded / 1e6).toFixed(1)} MB</span>
            </div>
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {report && (
          <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/30 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">
                {report.complete ? "Import complete" : "Importing…"}
              </span>
              <span className="text-xs text-muted-foreground">
                {report.done}/{report.chunks}{report.failed > 0 ? ` · ${report.failed} failed` : ""}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
              <span className="text-success">+{report.hands_added.toLocaleString("en-US")} hands</span>
              <span className="text-muted-foreground">{report.hands_skipped.toLocaleString("en-US")} duplicate hands skipped</span>
              <span className="text-success">+{report.tournaments_added.toLocaleString("en-US")} tournaments</span>
              <span className="text-muted-foreground">{report.tournaments_skipped.toLocaleString("en-US")} duplicate tournaments skipped</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
