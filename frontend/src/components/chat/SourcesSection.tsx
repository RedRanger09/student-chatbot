"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { BookOpen, FileText, FolderOpen, NotebookPen } from "lucide-react";
import type { Citation } from "@/lib/citations";
import { prettyDocumentTitle } from "@/lib/citations";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { SourceDialog } from "@/components/chat/SourceDialog";

type SourcesSectionProps = {
  citations: Citation[];
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
      {uploaded ? "Uploaded Notes" : "Institutional"}
    </Badge>
  );
}

export function SourcesSection({ citations }: SourcesSectionProps) {
  const [active, setActive] = useState<Citation | null>(null);
  const [open, setOpen] = useState(false);

  if (!citations.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="mt-3 w-full max-w-[min(100%,42rem)]"
    >
      <Separator className="mb-3" />
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--ink)]">
        <BookOpen className="h-4 w-4 text-[var(--accent-deep)]" />
        Sources
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {citations.map((citation) => {
          const Icon =
            citation.source_type === "uploaded_notes" ? NotebookPen : FileText;
          return (
            <button
              key={citation.id || citation.document}
              type="button"
              onClick={() => {
                setActive(citation);
                setOpen(true);
              }}
              className="text-left"
            >
              <Card className="transition-colors hover:border-[var(--accent)] hover:bg-[var(--accent-soft)]/40">
                <CardContent className="space-y-2 p-3">
                  <div className="flex items-start gap-2">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-deep)]" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {prettyDocumentTitle(citation.document)}
                      </p>
                      <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-[var(--muted)]">
                        <FolderOpen className="h-3 w-3" />
                        {citation.category || "General"}
                      </p>
                    </div>
                  </div>
                  <SourceTypeBadge sourceType={citation.source_type} />
                </CardContent>
              </Card>
            </button>
          );
        })}
      </div>

      <SourceDialog
        citation={active}
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setActive(null);
        }}
      />
    </motion.div>
  );
}
