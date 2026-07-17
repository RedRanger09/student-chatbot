/** Citation / inspector helpers shared by chat UI components. */

export type CitationPassage = {
  chunk_id: string;
  text: string;
  similarity: number;
};

export type Citation = {
  id: string;
  document: string;
  category: string;
  chunk_ids: string[];
  similarity: number;
  source_type: "institutional" | "uploaded_notes" | string;
  retrieved_text: string;
  passages?: CitationPassage[];
  metadata?: Record<string, unknown>;
};

export type InspectorMeta = {
  intent?: string;
  confidence?: number;
  provider?: string | null;
  model?: string | null;
  retrieved_count?: number;
  referenced_documents?: string[];
  referenced_chunk_ids?: string[];
  top_similarity?: number | null;
  context_characters?: number;
  context_chunks?: number;
  prompt_length?: number;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  generation_latency_ms?: number;
  search_latency_ms?: number;
  latency_ms?: number;
  source_type?: string;
  knowledge_mode?: string | null;
  knowledge_mode_reason?: string | null;
  fallback_used?: boolean;
  retrieval_succeeded?: boolean;
  safety_decision?: string | null;
  generation_blocked?: boolean;
  escalation_category?: string | null;
  escalation_category_label?: string | null;
  escalation_severity?: string | null;
  ticket_created?: boolean;
  ticket_id?: string | null;
  support_resource?: Record<string, unknown> | null;
  citations?: Citation[];
  chunks?: Array<Record<string, unknown>>;
  citation_stats?: Record<string, unknown>;
  provider_selection?: Record<string, unknown>;
  reason?: string;
  history_messages_used?: number;
  conversation_context_length?: number;
  streaming_enabled?: boolean;
  streaming_duration_ms?: number | null;
  follow_ups?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

const INSPECTOR_KEY = "ssa_ai_inspector_enabled";
const SOURCES_KEY = "ssa_sources_enabled";

export function getAIInspectorEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(INSPECTOR_KEY) === "1";
  } catch {
    return false;
  }
}

export function setAIInspectorEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(INSPECTOR_KEY, enabled ? "1" : "0");
    window.dispatchEvent(
      new CustomEvent("ssa:ai-inspector", { detail: { enabled } }),
    );
  } catch {
    // ignore storage failures
  }
}

/** Sources panel under replies. Defaults to ON when unset. */
export function getSourcesEnabled(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const raw = window.localStorage.getItem(SOURCES_KEY);
    if (raw === null) return true;
    return raw === "1";
  } catch {
    return true;
  }
}

export function setSourcesEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SOURCES_KEY, enabled ? "1" : "0");
    window.dispatchEvent(
      new CustomEvent("ssa:sources", { detail: { enabled } }),
    );
  } catch {
    // ignore storage failures
  }
}

export function prettyDocumentTitle(document: string): string {
  const base = (document || "Unknown").replace(/\\/g, "/").split("/").pop() || "Unknown";
  const stem = base.replace(/\.[^.]+$/, "");
  return stem
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function extractCitations(meta?: Record<string, unknown> | null): Citation[] {
  if (!meta) return [];
  const raw = meta.citations;
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is Citation => {
    return (
      !!item &&
      typeof item === "object" &&
      typeof (item as Citation).document === "string"
    );
  });
}

export function extractInspectorMeta(
  meta?: Record<string, unknown> | null,
): InspectorMeta {
  return (meta || {}) as InspectorMeta;
}
