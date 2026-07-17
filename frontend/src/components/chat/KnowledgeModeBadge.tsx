"use client";

import { BookOpen, FileText, Shield, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export type KnowledgeBadge = {
  kind: string;
  label: string;
  emoji?: string;
  disclaimer?: string;
};

type KnowledgeModeBadgeProps = {
  badge?: KnowledgeBadge | null;
  compact?: boolean;
};

type Tone = {
  chip: string;
  Icon: typeof Sparkles;
  displayLabel: string;
};

function resolveTone(kind: string, fallbackLabel: string): Tone {
  if (kind === "general_ai") {
    return {
      chip: "border-amber-200/70 bg-amber-50/90 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100",
      Icon: Sparkles,
      displayLabel: "General AI",
    };
  }
  if (kind === "uploaded_notes") {
    return {
      chip: "border-emerald-200/70 bg-emerald-50/90 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100",
      Icon: FileText,
      displayLabel: "Uploaded Notes",
    };
  }
  if (kind === "safety" || kind === "escalation") {
    return {
      chip: "border-rose-200/70 bg-rose-50/90 text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-100",
      Icon: Shield,
      displayLabel: "Safety",
    };
  }
  return {
    chip: "border-sky-200/70 bg-sky-50/90 text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100",
    Icon: BookOpen,
    displayLabel:
      kind === "knowledge_base" ? "Institutional RAG" : fallbackLabel || "Knowledge Base",
  };
}

export function KnowledgeModeBadge({
  badge,
  compact = false,
}: KnowledgeModeBadgeProps) {
  if (!badge || !badge.label) return null;
  const tone = resolveTone(badge.kind, badge.label);
  const Icon = tone.Icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className={compact ? "inline-flex" : "mb-0 space-y-1"}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            role="status"
            aria-label={`Knowledge mode: ${tone.displayLabel}`}
            className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-tight ${tone.chip}`}
          >
            <Icon className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
            <span className="truncate">{tone.displayLabel}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          {badge.disclaimer || `${tone.displayLabel} response`}
        </TooltipContent>
      </Tooltip>
      {!compact && badge.kind === "general_ai" && badge.disclaimer ? (
        <p className="text-[11px] leading-snug text-[var(--muted)]">
          {badge.disclaimer}
        </p>
      ) : null}
    </motion.div>
  );
}

export function extractKnowledgeBadge(
  meta?: Record<string, unknown> | null,
): KnowledgeBadge | null {
  if (!meta) return null;

  if (meta.generation_blocked === true || meta.safety_decision === "blocked_escalate") {
    return {
      kind: "safety",
      label: "Safety",
      emoji: "🛡",
      disclaimer: "This reply was handled by the safety layer with campus support resources.",
    };
  }

  const raw = meta.knowledge_badge;
  if (raw && typeof raw === "object") {
    const badge = raw as KnowledgeBadge;
    if (badge.label) return badge;
  }

  const mode = meta.knowledge_mode;
  if (mode === "general_ai") {
    return {
      kind: "general_ai",
      label: "General AI Knowledge",
      emoji: "✨",
      disclaimer:
        "This answer is based on the AI model's general knowledge and was not found in the institutional knowledge base.",
    };
  }
  if (mode === "grounded") {
    const sourceType = meta.source_type;
    if (sourceType === "uploaded_notes") {
      return { kind: "uploaded_notes", label: "Uploaded Notes", emoji: "📄" };
    }
    return { kind: "knowledge_base", label: "Knowledge Base", emoji: "📚" };
  }
  return null;
}
