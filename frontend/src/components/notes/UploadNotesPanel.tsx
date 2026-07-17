"use client";

import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, FileUp, Replace, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import {
  ApiError,
  clearSession,
  createSession,
  uploadDocument,
  type UploadResponse,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

type UploadNotesPanelProps = {
  sessionId: string | null;
  upload: UploadResponse | null;
  onSessionChange: (sessionId: string | null) => void;
  onUploadChange: (upload: UploadResponse | null) => void;
  /** Compact layout for the left sidebar. */
  compact?: boolean;
};

export function UploadNotesPanel({
  sessionId,
  upload,
  onSessionChange,
  onUploadChange,
  compact = false,
}: UploadNotesPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    const created = await createSession();
    onSessionChange(created.session_id);
    return created.session_id;
  }

  async function handleFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      const result = await uploadDocument(sid, file);
      onUploadChange(result);
      toast.success("Notes uploaded", {
        description: `${result.document_name} · ${result.chunk_count} sections indexed`,
      });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleRemove() {
    if (!sessionId) {
      onUploadChange(null);
      return;
    }
    setBusy(true);
    try {
      await clearSession(sessionId);
      onUploadChange(null);
      toast.message("Notes removed from this session");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not remove notes");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Upload className="h-3.5 w-3.5 text-[var(--accent-deep)]" />
          Upload notes
        </div>
        <Badge className="text-[10px]">Optional</Badge>
      </div>
      <p className="text-xs text-[var(--muted)]">
        PDF, DOCX, or TXT for personal study help.
      </p>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt"
        className="hidden"
        onChange={(e) => void handleFile(e.target.files?.[0] ?? null)}
      />

      <AnimatePresence mode="wait">
        {!upload ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-2)] px-3 py-3 text-center"
          >
            <FileUp className="mx-auto mb-2 h-4 w-4 text-[var(--muted)]" />
            <p className="mb-2 text-xs text-[var(--muted)]">No notes uploaded.</p>
            <Button
              size="sm"
              className="w-full"
              disabled={busy}
              onClick={() => inputRef.current?.click()}
            >
              <Upload className="h-3.5 w-3.5" />
              {busy ? "Uploading…" : "Upload"}
            </Button>
          </motion.div>
        ) : (
          <motion.div
            key="ready"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface-2)] p-3"
          >
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--ok)]" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{upload.document_name}</p>
                <p className="text-xs text-[var(--muted)]">
                  Indexed · {upload.chunk_count} section
                  {upload.chunk_count === 1 ? "" : "s"}
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                className="flex-1"
                disabled={busy}
                onClick={() => inputRef.current?.click()}
              >
                <Replace className="h-3.5 w-3.5" />
                Replace
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="flex-1"
                disabled={busy}
                onClick={() => void handleRemove()}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Remove
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
