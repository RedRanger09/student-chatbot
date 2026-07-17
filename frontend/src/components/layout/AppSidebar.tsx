"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  FileText,
  History,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import type { ConversationSummary, UploadResponse } from "@/lib/api";
import { UploadNotesPanel } from "@/components/notes/UploadNotesPanel";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type AppSidebarProps = {
  open: boolean;
  loading: boolean;
  conversations: ConversationSummary[];
  activeId: string | null;
  sessionId: string | null;
  upload: UploadResponse | null;
  onToggle: () => void;
  onNewChat: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onSessionChange: (sessionId: string | null) => void;
  onUploadChange: (upload: UploadResponse | null) => void;
};

export function AppSidebar({
  open,
  loading,
  conversations,
  activeId,
  sessionId,
  upload,
  onToggle,
  onNewChat,
  onSelect,
  onDelete,
  onSessionChange,
  onUploadChange,
}: AppSidebarProps) {
  return (
    <aside className="relative flex h-full shrink-0">
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="sidebar"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="overflow-hidden border-r border-[var(--line)] bg-[var(--sidebar)] transition-colors duration-200"
          >
            <div className="flex h-full w-[280px] flex-col">
              <div className="flex items-center justify-between gap-2 px-3 py-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <History className="h-4 w-4 text-[var(--accent-deep)]" />
                  Conversations
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon" onClick={onToggle}>
                      <PanelLeftClose className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Hide sidebar</TooltipContent>
                </Tooltip>
              </div>

              <div className="px-3 pb-3">
                <Button className="w-full" onClick={onNewChat}>
                  <Plus className="h-4 w-4" />
                  New chat
                </Button>
              </div>

              <Separator />

              <ScrollArea className="min-h-0 flex-1 px-2 py-3">
                {loading ? (
                  <div className="space-y-2 px-1">
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : conversations.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[var(--line)] px-3 py-6 text-center">
                    <MessageCircle className="mx-auto mb-2 h-5 w-5 text-[var(--muted)]" />
                    <p className="text-sm text-[var(--muted)]">
                      No conversations yet. Start a new chat to begin.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {conversations.map((item) => {
                      const active = item.id === activeId;
                      return (
                        <div
                          key={item.id}
                          className={`group flex items-center gap-1 rounded-xl px-2 py-2 transition-colors duration-200 ${
                            active
                              ? "bg-[var(--accent-soft)]"
                              : "hover:bg-[var(--surface-2)]"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => onSelect(item.id)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <div className="flex items-center gap-2">
                              <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--muted)]" />
                              <span className="truncate text-sm font-medium">
                                {item.title}
                              </span>
                            </div>
                            <p className="mt-0.5 truncate pl-5 text-xs text-[var(--muted)]">
                              {item.preview}
                            </p>
                          </button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                            onClick={() => onDelete(item.id)}
                            aria-label="Delete conversation"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </ScrollArea>

              <Separator />

              <div className="shrink-0 px-3 py-3">
                <UploadNotesPanel
                  compact
                  sessionId={sessionId}
                  upload={upload}
                  onSessionChange={onSessionChange}
                  onUploadChange={onUploadChange}
                />
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="collapsed"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex w-12 flex-col items-center gap-2 border-r border-[var(--line)] bg-[var(--sidebar)] py-3"
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={onToggle}>
                  <PanelLeftOpen className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Show sidebar</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={onNewChat}>
                  <Plus className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>New chat</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onToggle}
                  aria-label="Upload notes"
                >
                  <Upload className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {upload ? `Notes: ${upload.document_name}` : "Upload notes"}
              </TooltipContent>
            </Tooltip>
          </motion.div>
        )}
      </AnimatePresence>
    </aside>
  );
}
