"use client";

import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import type { InspectorMeta } from "@/lib/citations";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

type AIInspectorProps = {
  meta: InspectorMeta;
};

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[9.5rem_1fr] gap-2 text-xs">
      <span className="font-medium text-[var(--muted)]">{label}</span>
      <span className="min-w-0 break-words text-[var(--ink-soft)]">{value}</span>
    </div>
  );
}

function fmt(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(digits);
  return String(value);
}

export function AIInspector({ meta }: AIInspectorProps) {
  const [open, setOpen] = useState(false);
  const citations = Array.isArray(meta.citations) ? meta.citations : [];
  const chunks = Array.isArray(meta.chunks) ? meta.chunks : [];
  const docs = Array.isArray(meta.referenced_documents)
    ? meta.referenced_documents
    : citations.map((c) => c.document);
  const chunkIds = Array.isArray(meta.referenced_chunk_ids)
    ? meta.referenced_chunk_ids
    : citations.flatMap((c) => c.chunk_ids || []);
  const similarities = citations.map((c) => c.similarity);

  return (
    <div className="mt-2 w-full max-w-[min(100%,42rem)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-lg border border-dashed border-[var(--line)] bg-[var(--surface-2)] px-2.5 py-1.5 text-left text-xs font-medium text-[var(--muted)] hover:bg-[var(--surface-3)]"
      >
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="inline-flex"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </motion.span>
        AI Inspector
        <Badge className="ml-auto text-[10px]">Developer</Badge>
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <Card className="mt-2 border-dashed shadow-none">
              <CardContent className="space-y-3 p-3">
                <div className="space-y-1.5">
                  <Row label="Intent" value={fmt(meta.intent)} />
                  <Row label="Confidence" value={fmt(meta.confidence, 3)} />
                  <Row label="Knowledge Mode" value={fmt(meta.knowledge_mode)} />
                  <Row
                    label="Mode Reason"
                    value={fmt(meta.knowledge_mode_reason)}
                  />
                  <Row
                    label="Fallback Used"
                    value={meta.fallback_used ? "yes" : "no"}
                  />
                  <Row
                    label="Retrieval OK"
                    value={meta.retrieval_succeeded ? "yes" : "no"}
                  />
                  <Row label="LLM Provider" value={fmt(meta.provider)} />
                  <Row label="Model Name" value={fmt(meta.model)} />
                  <Row label="Provider Used" value={fmt(meta.provider)} />
                  <Row label="Source Type" value={fmt(meta.source_type)} />
                </div>

                <Separator />

                <div className="space-y-1.5">
                  <Row label="Safety Decision" value={fmt(meta.safety_decision)} />
                  <Row
                    label="Escalation Category"
                    value={fmt(
                      meta.escalation_category_label || meta.escalation_category,
                    )}
                  />
                  <Row label="Severity" value={fmt(meta.escalation_severity)} />
                  <Row
                    label="Ticket Created"
                    value={meta.ticket_created ? "yes" : "no"}
                  />
                  <Row label="Ticket ID" value={fmt(meta.ticket_id)} />
                  <Row
                    label="Support Resource"
                    value={
                      meta.support_resource &&
                      typeof meta.support_resource === "object" &&
                      "name" in meta.support_resource
                        ? String(
                            (meta.support_resource as { name?: string }).name ||
                              "—",
                          )
                        : "—"
                    }
                  />
                  <Row
                    label="Generation Blocked"
                    value={meta.generation_blocked ? "yes" : "no"}
                  />
                </div>

                <Separator />

                <div className="space-y-1.5">
                  <Row label="Retrieved Chunks" value={fmt(meta.retrieved_count ?? chunks.length)} />
                  <Row
                    label="Referenced Docs"
                    value={docs.length ? docs.join(", ") : "—"}
                  />
                  <Row
                    label="Chunk IDs"
                    value={
                      chunkIds.length ? (
                        <span className="font-mono">{chunkIds.join(", ")}</span>
                      ) : (
                        "—"
                      )
                    }
                  />
                  <Row
                    label="Similarity Scores"
                    value={
                      similarities.length
                        ? similarities.map((s) => Number(s).toFixed(3)).join(", ")
                        : "—"
                    }
                  />
                  <Row label="Highest Similarity" value={fmt(meta.top_similarity, 4)} />
                  <Row label="Context Length" value={fmt(meta.context_characters)} />
                  <Row label="Context Chunks" value={fmt(meta.context_chunks)} />
                  <Row label="Prompt Length" value={fmt(meta.prompt_length)} />
                </div>

                <Separator />

                <div className="space-y-1.5">
                  <Row label="Prompt Tokens" value={fmt(meta.prompt_tokens)} />
                  <Row label="Completion Tokens" value={fmt(meta.completion_tokens)} />
                  <Row label="Total Tokens" value={fmt(meta.total_tokens)} />
                  <Row label="Generation Latency" value={`${fmt(meta.generation_latency_ms)} ms`} />
                  <Row label="Retrieval Latency" value={`${fmt(meta.search_latency_ms)} ms`} />
                  <Row label="Total Latency" value={`${fmt(meta.latency_ms)} ms`} />
                </div>

                <Separator />

                <div className="space-y-1.5">
                  <Row
                    label="Conversation Context Length"
                    value={fmt(meta.conversation_context_length)}
                  />
                  <Row
                    label="History Messages Used"
                    value={fmt(meta.history_messages_used)}
                  />
                  <Row
                    label="Streaming Enabled"
                    value={meta.streaming_enabled ? "yes" : "no"}
                  />
                  <Row
                    label="Streaming Duration"
                    value={
                      meta.streaming_duration_ms != null
                        ? `${fmt(meta.streaming_duration_ms)} ms`
                        : "—"
                    }
                  />
                </div>

                <Separator />

                <div>
                  <p className="mb-1.5 text-xs font-semibold text-[var(--muted)]">
                    Citation Metadata
                  </p>
                  <ScrollArea className="max-h-48 rounded-lg border border-[var(--line)] bg-[var(--surface-2)]">
                    <pre className="p-2 font-mono text-[10px] leading-relaxed text-[var(--ink-soft)]">
                      {JSON.stringify(
                        {
                          citations,
                          citation_stats: meta.citation_stats,
                          provider_selection: meta.provider_selection,
                          reason: meta.reason,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </ScrollArea>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
