"use client";

import { motion } from "framer-motion";
import {
  Bot,
  Check,
  Copy,
  RefreshCw,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  User,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { ChatMessage } from "@/lib/api";
import { extractFollowUps } from "@/lib/api";
import {
  extractCitations,
  extractInspectorMeta,
} from "@/lib/citations";
import { formatTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AIInspector } from "@/components/chat/AIInspector";
import { FollowUpChips } from "@/components/chat/FollowUpChips";
import { MarkdownMessage } from "@/components/chat/MarkdownMessage";
import {
  buildMessageMeta,
  ModelIndicator,
} from "@/components/chat/ModelIndicator";
import { SourcesSection } from "@/components/chat/SourcesSection";
import {
  extractSupportResource,
  SupportResourcesCard,
} from "@/components/chat/SupportResourcesCard";
import { TypingIndicator } from "@/components/chat/TypingIndicator";

type FeedbackValue = "like" | "dislike" | null;

type ChatMessageBubbleProps = {
  message: ChatMessage;
  onRegenerate?: () => void;
  onRetry?: () => void;
  onFollowUp?: (prompt: string) => void;
  aiInspectorEnabled?: boolean;
  sourcesEnabled?: boolean;
  streaming?: boolean;
  showFollowUps?: boolean;
  actionsDisabled?: boolean;
};

function feedbackKey(messageId: string) {
  return `ssa_feedback_${messageId}`;
}

export function ChatMessageBubble({
  message,
  onRegenerate,
  onRetry,
  onFollowUp,
  aiInspectorEnabled = false,
  sourcesEnabled = true,
  streaming = false,
  showFollowUps = true,
  actionsDisabled = false,
}: ChatMessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackValue>(null);
  const citations = extractCitations(message.meta);
  const inspectorMeta = extractInspectorMeta(message.meta);
  const messageMeta = buildMessageMeta(message.meta);
  const supportResource = extractSupportResource(message.meta);
  const followUps = extractFollowUps(message.meta);
  const showSources =
    !isUser && !streaming && sourcesEnabled && citations.length > 0;
  const showSupport = !isUser && !streaming && !!supportResource;
  const showInspector = !isUser && !streaming && aiInspectorEnabled;
  const showChips =
    !isUser && !streaming && showFollowUps && followUps.length > 0;
  const showMeta =
    !isUser &&
    !streaming &&
    (!!messageMeta.provider ||
      !!messageMeta.model ||
      !!messageMeta.knowledgeBadge);
  const categoryLabel =
    typeof message.meta?.escalation_category_label === "string"
      ? message.meta.escalation_category_label
      : typeof message.meta?.escalation_category === "string"
        ? message.meta.escalation_category
        : null;
  const severity =
    typeof message.meta?.escalation_severity === "string"
      ? message.meta.escalation_severity
      : null;

  useEffect(() => {
    if (isUser || typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(feedbackKey(message.id));
      if (raw === "like" || raw === "dislike") setFeedback(raw);
    } catch {
      // ignore
    }
  }, [isUser, message.id]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // ignore clipboard failures
    }
  }

  function setFeedbackValue(value: FeedbackValue) {
    const next = feedback === value ? null : value;
    setFeedback(next);
    try {
      if (next) window.localStorage.setItem(feedbackKey(message.id), next);
      else window.localStorage.removeItem(feedbackKey(message.id));
    } catch {
      // ignore
    }
  }

  return (
    <motion.div
      id={`msg-${message.id}`}
      data-message-id={message.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser ? (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent-deep)] shadow-[var(--shadow-soft)]">
          <Bot className="h-4 w-4" />
        </div>
      ) : null}

      <div
        className={`max-w-[min(100%,42rem)] ${isUser ? "items-end" : "items-start"}`}
      >
        {showMeta ? (
          <ModelIndicator
            provider={messageMeta.provider}
            model={messageMeta.model}
            knowledgeBadge={messageMeta.knowledgeBadge}
          />
        ) : null}

        <div
          className={
            isUser
              ? "rounded-2xl rounded-br-md bg-[var(--bubble-user)] px-4 py-3 text-white shadow-[var(--shadow-soft)]"
              : "rounded-2xl rounded-bl-md border border-[var(--line)] bg-[var(--bubble-assistant)] px-4 py-3.5 shadow-[var(--shadow-soft)]"
          }
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-[0.95rem] leading-relaxed">
              {message.content}
            </p>
          ) : message.content ? (
            <div className="relative">
              <MarkdownMessage content={message.content} />
              {streaming ? (
                <span
                  className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[2px] animate-pulse bg-[var(--accent)] align-baseline"
                  aria-hidden
                />
              ) : null}
            </div>
          ) : streaming ? (
            <TypingIndicator />
          ) : (
            <p className="text-sm text-[var(--muted)]">No content</p>
          )}
        </div>

        {showSupport && supportResource ? (
          <SupportResourcesCard
            resource={supportResource}
            categoryLabel={categoryLabel}
            severity={severity}
          />
        ) : null}
        {showSources ? <SourcesSection citations={citations} /> : null}
        {showChips && onFollowUp ? (
          <FollowUpChips
            items={followUps}
            disabled={actionsDisabled}
            onSelect={onFollowUp}
          />
        ) : null}
        {showInspector ? <AIInspector meta={inspectorMeta} /> : null}

        <div
          className={`mt-1.5 flex items-center gap-0.5 ${isUser ? "justify-end" : "justify-start"}`}
        >
          <span className="mr-1 text-[11px] text-[var(--muted)]">
            {formatTime(message.created_at)}
          </span>
          {!isUser && !streaming ? (
            <>
              <ActionButton
                label="Copy"
                onClick={handleCopy}
                icon={
                  copied ? (
                    <Check className="h-3.5 w-3.5 text-[var(--ok)]" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )
                }
              />
              <ActionButton
                label="Regenerate"
                onClick={onRegenerate}
                icon={<RefreshCw className="h-3.5 w-3.5" />}
              />
              <ActionButton
                label="Retry"
                onClick={onRetry || onRegenerate}
                icon={<RotateCcw className="h-3.5 w-3.5" />}
              />
              <ActionButton
                label="Like"
                onClick={() => setFeedbackValue("like")}
                active={feedback === "like"}
                icon={<ThumbsUp className="h-3.5 w-3.5" />}
              />
              <ActionButton
                label="Dislike"
                onClick={() => setFeedbackValue("dislike")}
                active={feedback === "dislike"}
                icon={<ThumbsDown className="h-3.5 w-3.5" />}
              />
            </>
          ) : null}
        </div>
      </div>

      {isUser ? (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--surface-3)] text-[var(--ink-soft)] shadow-[var(--shadow-soft)]">
          <User className="h-4 w-4" />
        </div>
      ) : null}
    </motion.div>
  );
}

function ActionButton({
  label,
  icon,
  onClick,
  active = false,
}: {
  label: string;
  icon: ReactNode;
  onClick?: () => void;
  active?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={`h-7 w-7 transition-colors duration-200 ${
            active ? "text-[var(--accent-deep)]" : "text-[var(--muted)]"
          }`}
          onClick={onClick}
          aria-label={label}
          disabled={!onClick}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
