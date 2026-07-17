"use client";

import { Cloud, Cpu, Sparkles } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  extractKnowledgeBadge,
  KnowledgeModeBadge,
  type KnowledgeBadge,
} from "@/components/chat/KnowledgeModeBadge";

export type ModelIndicatorProps = {
  provider?: string | null;
  model?: string | null;
  knowledgeBadge?: KnowledgeBadge | null;
  className?: string;
};

type ProviderVisual = {
  label: string;
  dotClass: string;
  chipClass: string;
  Icon: typeof Sparkles;
  tooltip: (modelLabel: string) => string;
};

function resolveProviderVisual(provider?: string | null): ProviderVisual {
  const raw = (provider || "").trim().toLowerCase();

  if (
    raw === "gemini" ||
    raw === "google" ||
    raw.includes("gemini") ||
    raw.includes("google")
  ) {
    return {
      label: "Gemini",
      dotClass: "bg-sky-500",
      chipClass:
        "border-sky-200/70 bg-sky-50/90 text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100",
      Icon: Cloud,
      tooltip: (model) => `Generated using ${model} via Google AI.`,
    };
  }

  if (
    raw === "lmstudio" ||
    raw === "lm_studio" ||
    raw.includes("lmstudio") ||
    raw.includes("lm studio")
  ) {
    return {
      label: "Local",
      dotClass: "bg-emerald-500",
      chipClass:
        "border-emerald-200/70 bg-emerald-50/90 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100",
      Icon: Cpu,
      tooltip: (model) =>
        `Generated using ${model} via the configured local AI endpoint (online).`,
    };
  }

  if (raw === "local" || raw.includes("local") || raw.includes("ollama")) {
    return {
      label: "Local",
      dotClass: "bg-emerald-500",
      chipClass:
        "border-emerald-200/70 bg-emerald-50/90 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100",
      Icon: Cpu,
      tooltip: (model) => `Generated using ${model} running locally.`,
    };
  }

  if (!raw) {
    return {
      label: "AI",
      dotClass: "bg-[var(--muted)]",
      chipClass:
        "border-[var(--line)] bg-[var(--surface-2)] text-[var(--muted)]",
      Icon: Sparkles,
      tooltip: (model) => `Generated using ${model}.`,
    };
  }

  const label = String(provider)
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    label,
    dotClass: "bg-[var(--muted)]",
    chipClass:
      "border-[var(--line)] bg-[var(--surface-2)] text-[var(--ink-soft)]",
    Icon: Sparkles,
    tooltip: (model) => `Generated using ${model} via ${label}.`,
  };
}

function displayModelName(model?: string | null): string {
  const raw = (model || "").trim();
  if (!raw) return "Unknown model";
  return raw.replace(/\s+/g, " ");
}

export function ModelIndicator({
  provider,
  model,
  knowledgeBadge,
  className = "",
}: ModelIndicatorProps) {
  const hasProvider = !!(provider && String(provider).trim());
  const hasModel = !!(model && String(model).trim());
  const hasKnowledge = !!(knowledgeBadge && knowledgeBadge.label);
  if (!hasProvider && !hasModel && !hasKnowledge) return null;

  const visual = resolveProviderVisual(provider);
  const modelLabel = displayModelName(model);
  const showModelChip = hasProvider || hasModel;
  const aria = showModelChip
    ? `Answering model: ${visual.label}, ${modelLabel}`
    : undefined;
  const tooltip = visual.tooltip(modelLabel);
  const Icon = visual.Icon;

  return (
    <div
      className={`mb-2 flex max-w-full flex-wrap items-center gap-1.5 ${className}`.trim()}
    >
      {showModelChip ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              role="status"
              aria-label={aria}
              className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-tight opacity-95 ${visual.chipClass}`}
            >
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${visual.dotClass}`}
                aria-hidden
              />
              <Icon className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
              <span className="truncate">
                {visual.label}
                <span className="mx-1 opacity-45" aria-hidden>
                  •
                </span>
                <span className="font-normal opacity-90">{modelLabel}</span>
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            {tooltip}
          </TooltipContent>
        </Tooltip>
      ) : null}

      {hasKnowledge ? (
        <KnowledgeModeBadge badge={knowledgeBadge} compact />
      ) : null}
    </div>
  );
}

export function extractModelIndicator(
  meta?: Record<string, unknown> | null,
): { provider: string | null; model: string | null } | null {
  if (!meta) return null;
  const provider =
    typeof meta.provider === "string" && meta.provider.trim()
      ? meta.provider.trim()
      : null;
  const model =
    typeof meta.model === "string" && meta.model.trim()
      ? meta.model.trim()
      : null;
  if (!provider && !model) return null;
  return { provider, model };
}

export function buildMessageMeta(
  meta?: Record<string, unknown> | null,
): {
  provider: string | null;
  model: string | null;
  knowledgeBadge: KnowledgeBadge | null;
} {
  const modelInfo = extractModelIndicator(meta);
  return {
    provider: modelInfo?.provider ?? null,
    model: modelInfo?.model ?? null,
    knowledgeBadge: extractKnowledgeBadge(meta),
  };
}
