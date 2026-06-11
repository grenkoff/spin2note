"use client";

import * as React from "react";
import { UploadCloud } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { uploadFile, type UploadResult } from "@/lib/api";
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
  const [files, setFiles] = React.useState<FileList | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [results, setResults] = React.useState<UploadResult[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  async function submit() {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const out: UploadResult[] = [];
      for (const file of Array.from(files)) {
        out.push(await uploadFile(token, file));
      }
      setResults(out);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <h1 className="text-xl font-semibold">Upload hand histories</h1>
      <Card>
        <CardHeader>
          <CardTitle>Hand history or tournament summary files (.txt)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <input
            type="file"
            multiple
            accept=".txt"
            onChange={(e) => setFiles(e.target.files)}
            className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-2 file:text-sm file:text-foreground"
          />
          <Button onClick={submit} disabled={busy || !files}>
            <UploadCloud className="h-4 w-4" /> {busy ? "Uploading…" : "Upload"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {results.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Queued {results.length} file(s) for parsing. Stats refresh on the dashboard once the
              worker processes them.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
