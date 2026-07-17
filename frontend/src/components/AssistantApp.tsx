"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { GraduationCap } from "lucide-react";
import { toast } from "sonner";
import {
  ApiError,
  clearConversation,
  createConversation,
  deleteConversation,
  getConversation,
  getHealth,
  listConversations,
  streamChatMessage,
  type ChatMessage,
  type ConversationSummary,
  type HealthResponse,
  type UploadResponse,
} from "@/lib/api";
import { getAIInspectorEnabled, getSourcesEnabled } from "@/lib/citations";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { QuickActions } from "@/components/chat/QuickActions";
import { AISettingsDialog } from "@/components/settings/AISettingsDialog";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TooltipProvider } from "@/components/ui/tooltip";

export function AssistantApp() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [aiInspectorEnabled, setAiInspectorEnabledState] = useState(false);
  const [sourcesEnabled, setSourcesEnabledState] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollViewportRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const lastUserPrompt = useRef<string>("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setAiInspectorEnabledState(getAIInspectorEnabled());
    setSourcesEnabledState(getSourcesEnabled());
    const onInspector = (event: Event) => {
      const detail = (event as CustomEvent<{ enabled?: boolean }>).detail;
      setAiInspectorEnabledState(Boolean(detail?.enabled));
    };
    const onSources = (event: Event) => {
      const detail = (event as CustomEvent<{ enabled?: boolean }>).detail;
      setSourcesEnabledState(Boolean(detail?.enabled));
    };
    window.addEventListener("ssa:ai-inspector", onInspector as EventListener);
    window.addEventListener("ssa:sources", onSources as EventListener);
    return () => {
      window.removeEventListener("ssa:ai-inspector", onInspector as EventListener);
      window.removeEventListener("ssa:sources", onSources as EventListener);
    };
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const items = await listConversations();
      setConversations(items);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not load conversations",
      );
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
    void getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [refreshConversations]);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, streamingId]);

  useEffect(() => {
    const root = scrollViewportRef.current;
    if (!root) return;
    const viewport = root.querySelector(
      "[data-radix-scroll-area-viewport]",
    ) as HTMLElement | null;
    if (!viewport) return;
    const onScroll = () => {
      const distance =
        viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
      stickToBottomRef.current = distance < 80;
    };
    viewport.addEventListener("scroll", onScroll, { passive: true });
    return () => viewport.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "l") {
        event.preventDefault();
        void handleNewChat();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleNewChat() {
    try {
      abortRef.current?.abort();
      const created = await createConversation();
      setActiveId(created.id);
      setMessages([]);
      setDraft("");
      setStreamingId(null);
      setBusy(false);
      stickToBottomRef.current = true;
      await refreshConversations();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start chat");
    }
  }

  async function handleSelect(id: string) {
    try {
      const detail = await getConversation(id);
      setActiveId(detail.id);
      setMessages(detail.messages);
      setStreamingId(null);
      stickToBottomRef.current = true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not open chat");
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteConversation(id);
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
        setStreamingId(null);
      }
      await refreshConversations();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete chat");
    }
  }

  async function handleClear() {
    if (!activeId) {
      setMessages([]);
      return;
    }
    try {
      const cleared = await clearConversation(activeId);
      setMessages(cleared.messages);
      setStreamingId(null);
      await refreshConversations();
      toast.message("Conversation cleared");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not clear chat");
    }
  }

  async function submitMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    lastUserPrompt.current = trimmed;
    setBusy(true);
    setDraft("");
    stickToBottomRef.current = true;

    const optimisticUser: ChatMessage = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content: trimmed,
      created_at: Date.now() / 1000,
    };
    const provisionalAssistantId = `local-assistant-${Date.now()}`;
    const provisionalAssistant: ChatMessage = {
      id: provisionalAssistantId,
      role: "assistant",
      content: "",
      created_at: Date.now() / 1000,
      meta: { streaming: true },
    };

    setMessages((prev) => [...prev, optimisticUser, provisionalAssistant]);
    setStreamingId(provisionalAssistantId);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChatMessage(
        {
          message: trimmed,
          conversationId: activeId,
          sessionId,
          signal: controller.signal,
        },
        {
          onStart: (payload) => {
            setActiveId(payload.conversation_id);
            setMessages((prev) => {
              const withoutLocal = prev.filter(
                (m) =>
                  m.id !== optimisticUser.id && m.id !== provisionalAssistantId,
              );
              return [
                ...withoutLocal,
                payload.user_message,
                {
                  id: payload.assistant_message_id || provisionalAssistantId,
                  role: "assistant",
                  content: "",
                  created_at: Date.now() / 1000,
                  meta: {
                    streaming: true,
                    history_messages_used: payload.history_messages_used,
                    conversation_context_length:
                      payload.conversation_context_length,
                  },
                },
              ];
            });
            setStreamingId(payload.assistant_message_id || provisionalAssistantId);
          },
          onToken: (delta) => {
            setMessages((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i -= 1) {
                if (next[i].role === "assistant") {
                  next[i] = {
                    ...next[i],
                    content: `${next[i].content || ""}${delta}`,
                    meta: { ...(next[i].meta || {}), streaming: true },
                  };
                  break;
                }
              }
              return next;
            });
          },
          onDone: (response) => {
            setActiveId(response.conversation_id);
            const assistant: ChatMessage = {
              ...response.assistant_message,
              meta: {
                ...(response.metadata || {}),
                ...(response.assistant_message.meta || {}),
                streaming: false,
              },
            };
            setMessages((prev) => {
              const prior = prev.filter(
                (m) =>
                  m.id !== optimisticUser.id &&
                  m.id !== provisionalAssistantId &&
                  m.id !== response.user_message.id &&
                  m.id !== response.assistant_message.id &&
                  !(m.role === "assistant" && m.meta?.streaming),
              );
              return [...prior, response.user_message, assistant];
            });
            setStreamingId(null);
          },
        },
      );
      await refreshConversations();
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        return;
      }
      setMessages((prev) =>
        prev.filter(
          (m) =>
            m.id !== optimisticUser.id &&
            m.id !== provisionalAssistantId &&
            !(m.role === "assistant" && m.meta?.streaming),
        ),
      );
      setDraft(trimmed);
      setStreamingId(null);
      toast.error(err instanceof ApiError ? err.message : "Message failed");
    } finally {
      setBusy(false);
      setStreamingId(null);
      abortRef.current = null;
    }
  }

  function handleRegenerate() {
    if (!lastUserPrompt.current || busy) return;
    void submitMessage(lastUserPrompt.current);
  }

  function handleFollowUp(prompt: string) {
    if (busy) {
      setDraft(prompt);
      return;
    }
    void submitMessage(prompt);
  }

  const showEmpty = messages.length === 0 && !busy;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex h-[100dvh] overflow-hidden bg-[var(--canvas)] text-[var(--ink)]">
        <AppSidebar
          open={sidebarOpen}
          loading={listLoading}
          conversations={conversations}
          activeId={activeId}
          sessionId={sessionId}
          upload={upload}
          onToggle={() => setSidebarOpen((v) => !v)}
          onNewChat={() => void handleNewChat()}
          onSelect={(id) => void handleSelect(id)}
          onDelete={(id) => void handleDelete(id)}
          onSessionChange={setSessionId}
          onUploadChange={setUpload}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-[var(--line)] bg-[var(--surface)]/85 px-4 py-3 backdrop-blur-md transition-colors duration-200 md:px-6">
            <div className="min-w-0">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-deep)] shadow-[var(--shadow-soft)]">
                  <GraduationCap className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <h1 className="truncate font-[family-name:var(--font-display)] text-lg font-semibold tracking-tight md:text-xl">
                    Student Support Assistant
                  </h1>
                  <p className="truncate text-xs text-[var(--muted)] md:text-sm">
                    Campus help and study notes — in one calm place.
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge className="hidden border-[var(--line)] bg-[var(--surface-2)] sm:inline-flex">
                {health ? `Online · v${health.version}` : "Connecting…"}
              </Badge>
              <ThemeToggle />
              <AISettingsDialog />
            </div>
          </header>

          <div className="flex flex-1 min-h-0 justify-center px-3 py-4 sm:px-4 md:px-6">
            <main className="flex w-full max-w-3xl min-w-0 flex-col">
              <ScrollArea className="flex-1 pr-2" ref={scrollViewportRef}>
                <div className="flex flex-col gap-5 pb-4 pt-2">
                  {showEmpty ? (
                    <motion.section
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.22 }}
                      className="space-y-6"
                    >
                      <div className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] px-5 py-8 text-center shadow-[var(--shadow)] md:px-8">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--accent-deep)]">
                          AI Student Support
                        </p>
                        <h2 className="mt-2 font-[family-name:var(--font-display)] text-2xl font-semibold tracking-tight md:text-3xl">
                          How can I help you today?
                        </h2>
                        <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-[var(--muted)] md:text-base">
                          Ask about scholarships, hostel, exams, and more — or upload
                          notes from the left sidebar when you want help with your own
                          materials.
                        </p>
                      </div>
                      <QuickActions onSelect={(prompt) => setDraft(prompt)} />
                    </motion.section>
                  ) : (
                    <div className="space-y-5">
                      {listLoading && messages.length === 0 ? (
                        <div className="space-y-3">
                          {[0, 1, 2].map((i) => (
                            <div
                              key={i}
                              className="h-16 animate-pulse rounded-2xl bg-[var(--surface-3)]"
                            />
                          ))}
                        </div>
                      ) : null}
                      {messages.map((message, index) => {
                        const isLastAssistant =
                          message.role === "assistant" &&
                          index === messages.length - 1;
                        return (
                          <ChatMessageBubble
                            key={message.id}
                            message={message}
                            onRegenerate={
                              isLastAssistant ? handleRegenerate : undefined
                            }
                            onRetry={
                              isLastAssistant ? handleRegenerate : undefined
                            }
                            onFollowUp={handleFollowUp}
                            aiInspectorEnabled={aiInspectorEnabled}
                            sourcesEnabled={sourcesEnabled}
                            streaming={streamingId === message.id}
                            showFollowUps={isLastAssistant && !busy}
                            actionsDisabled={busy}
                          />
                        );
                      })}
                      <div ref={bottomRef} />
                    </div>
                  )}
                </div>
              </ScrollArea>

              <div className="w-full pt-3">
                {!showEmpty ? (
                  <div className="mb-3">
                    <QuickActions
                      compact
                      onSelect={(prompt) => setDraft(prompt)}
                    />
                  </div>
                ) : null}
                <ChatInput
                  value={draft}
                  busy={busy}
                  onChange={setDraft}
                  onSend={() => void submitMessage(draft)}
                  onClear={() => void handleClear()}
                  onNewChat={() => void handleNewChat()}
                />
                <p className="mt-2 text-center text-[11px] text-[var(--muted)]">
                  Enter to send · Shift+Enter for a new line · Ctrl+L new chat
                </p>
              </div>
            </main>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
