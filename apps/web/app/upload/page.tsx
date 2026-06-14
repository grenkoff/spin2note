"use client";

import * as React from "react";
import { FolderUp, UploadCloud } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getImportSummary, type ImportSummary } from "@/lib/api";
import { bulkUpload, type BulkProgress } from "@/lib/bulk-upload";
import { useAuth } from "@/lib/auth";

export default function UploadPage() {
  return (
    <AppShell>
      <Uploader />
    </AppShell>
  );
}

function Uploader() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";
  const folderRef = React.useRef<HTMLInputElement>(null);
  const filesRef = React.useRef<HTMLInputElement>(null);
  const [files, setFiles] = React.useState<File[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState<BulkProgress | null>(null);
  const [report, setReport] = React.useState<ImportSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  function pick(list: FileList | null) {
    if (!list) return;
    setFiles(Array.from(list).filter((f) => f.name.endsWith(".txt")));
    setReport(null);
    setProgress(null);
  }

  async function start() {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const { sessionId } = await bulkUpload(files, token, setProgress);
      // Parsing is async in the worker — poll the import report until all chunks finish.
      for (let i = 0; i < 600; i++) {
        const s = await getImportSummary(token, sessionId);
        setReport(s);
        if (s.complete) break;
        await new Promise((r) => setTimeout(r, 1500));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const pct = progress && progress.filesTotal > 0
    ? Math.round((progress.filesRead / progress.filesTotal) * 100)
    : 0;

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <h1 className="text-xl font-semibold">Upload your hand history</h1>
      <Card>
        <CardHeader>
          <CardTitle>Select a whole folder or many .txt files — even 100k+</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={() => folderRef.current?.click()} disabled={busy}>
              <FolderUp className="h-4 w-4" /> Choose folder
            </Button>
            <Button variant="outline" onClick={() => filesRef.current?.click()} disabled={busy}>
              <UploadCloud className="h-4 w-4" /> Choose files
            </Button>
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
              accept=".txt"
              className="hidden"
              onChange={(e) => pick(e.target.files)}
            />
          </div>

          {files.length > 0 && (
            <p className="text-sm text-muted-foreground">{files.length.toLocaleString("en-US")} .txt files selected</p>
          )}

          <Button onClick={start} disabled={busy || files.length === 0}>
            {busy ? "Uploading…" : "Upload"}
          </Button>

          {progress && (
            <div className="flex flex-col gap-2">
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>Read: {progress.filesRead.toLocaleString("en-US")} / {progress.filesTotal.toLocaleString("en-US")}</span>
                <span>Chunks: {progress.chunksUploaded} / {progress.chunksStarted}</span>
                <span>Sent: {(progress.bytesUploaded / 1e6).toFixed(1)} MB (gzip)</span>
                {progress.filesSkipped > 0 && <span>Skipped: {progress.filesSkipped}</span>}
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
                  {report.done}/{report.chunks} chunks{report.failed > 0 ? ` · ${report.failed} failed` : ""}
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
    </div>
  );
}
