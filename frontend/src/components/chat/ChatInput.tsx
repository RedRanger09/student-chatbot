"use client";

import { ArrowUp, Eraser, SquarePen } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type ChatInputProps = {
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onClear: () => void;
  onNewChat: () => void;
};

export function ChatInput({
  value,
  busy,
  onChange,
  onSend,
  onClear,
  onNewChat,
}: ChatInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-2.5 shadow-[var(--shadow)] transition-[box-shadow,border-color] duration-200 focus-within:border-[var(--accent)]/40 focus-within:shadow-[0_0_0_3px_var(--ring)]">
      <Textarea
        ref={ref}
        value={value}
        disabled={busy}
        placeholder="Ask about campus life, fees, exams, or your uploaded notes…"
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        className="min-h-[48px] border-0 bg-transparent px-2 shadow-none placeholder:text-[var(--muted)] focus-visible:ring-0"
        rows={1}
      />
      <div className="mt-1 flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onNewChat}
                aria-label="New chat"
                className="h-8 w-8 text-[var(--muted)] hover:text-[var(--ink)]"
              >
                <SquarePen className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>New chat (Ctrl+L)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onClear}
                aria-label="Clear conversation"
                className="h-8 w-8 text-[var(--muted)] hover:text-[var(--ink)]"
              >
                <Eraser className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Clear conversation</TooltipContent>
          </Tooltip>
          <span className="hidden text-[10px] text-[var(--muted)] sm:inline">
            Enter send · Shift+Enter newline
          </span>
        </div>
        <Button
          type="button"
          size="icon"
          disabled={busy || !value.trim()}
          onClick={onSend}
          aria-label="Send message"
          className="h-9 w-9 rounded-full shadow-[var(--shadow-soft)] transition-transform duration-150 enabled:hover:-translate-y-0.5"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
