"use client";

import { BookOpen, FileText, FolderOpen, NotebookPen } from "lucide-react";
import type { Citation } from "@/lib/citations";
import { prettyDocumentTitle } from "@/lib/citations";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

type SourceDialogProps = {
  citation: Citation | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function SourceTypeBadge({ sourceType }: { sourceType: string }) {
  const uploaded = sourceType === "uploaded_notes";
  return (
    <Badge
      className={
        uploaded
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-sky-200 bg-sky-50 text-sky-800"
      }
    >
      {uploaded ? "Uploaded Notes" : "Institutional KB"}
    </Badge>
  );
}

export function SourceDialog({ citation, open, onOpenChange }: SourceDialogProps) {
  if (!citation) return null;

  const title = prettyDocumentTitle(citation.document);
  const passages =
    citation.passages && citation.passages.length > 0
      ? citation.passages
      : [
          {
            chunk_id: citation.chunk_ids[0] || "unknown",
            text: citation.retrieved_text || "",
            similarity: citation.similarity,
          },
        ];
  const Icon =
    citation.source_type === "uploaded_notes" ? NotebookPen : BookOpen;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[min(94vw,640px)] overflow-hidden p-0">
        <div className="px-5 pt-5">
          <DialogHeader>
            <DialogTitle className="flex items-start gap-2">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent-deep)]" />
              <span>{title}</span>
            </DialogTitle>
            <DialogDescription>
              Retrieved passage details for this source. Similarity and chunk IDs
              are shown here for transparency.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="space-y-3 px-5 pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <SourceTypeBadge sourceType={citation.source_type} />
            <Badge className="gap-1">
              <FolderOpen className="h-3 w-3" />
              {citation.category || "General"}
            </Badge>
            <Badge>
              Similarity {Number(citation.similarity || 0).toFixed(3)}
            </Badge>
          </div>

          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-2)] px-3 py-2 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              Document
            </p>
            <p className="mt-0.5 flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5 text-[var(--muted)]" />
              {citation.document}
            </p>
          </div>

          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-2)] px-3 py-2 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              Referenced chunk IDs
            </p>
            <p className="mt-1 font-mono text-xs leading-relaxed text-[var(--ink-soft)]">
              {(citation.chunk_ids || []).join(", ") || "—"}
            </p>
          </div>
        </div>

        <Separator />

        <ScrollArea className="max-h-[40vh] px-5">
          <div className="space-y-3 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              Retrieved text
            </p>
            {passages.map((passage, index) => (
              <div
                key={`${passage.chunk_id}-${index}`}
                className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3"
              >
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                  <span className="font-mono">{passage.chunk_id}</span>
                  <span>·</span>
                  <span>{Number(passage.similarity || 0).toFixed(3)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--ink)]">
                  {passage.text || "No text available for this chunk."}
                </p>
              </div>
            ))}
          </div>
        </ScrollArea>

        {citation.metadata && Object.keys(citation.metadata).length > 0 ? (
          <>
            <Separator />
            <ScrollArea className="max-h-[18vh] px-5">
              <div className="space-y-2 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                  Metadata
                </p>
                <pre className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface-2)] p-3 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                  {JSON.stringify(citation.metadata, null, 2)}
                </pre>
              </div>
            </ScrollArea>
          </>
        ) : null}

        <div className="h-3" />
      </DialogContent>
    </Dialog>
  );
}
