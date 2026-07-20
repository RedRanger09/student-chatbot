/**
 * Central API client for the Student Support FastAPI backend.
 */

import { getClientId } from "@/lib/client-id";
import { getGeminiApiKey } from "@/lib/gemini-key";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system" | string;
  content: string;
  created_at: number;
  meta?: Record<string, unknown>;
};

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  preview: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: ChatMessage[];
};

export type ChatResponse = {
  conversation_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  mode: string;
  streaming_supported: boolean;
  metadata?: Record<string, unknown>;
  content?: string;
  status?: string;
  source?: string | null;
};

export type HealthResponse = {
  status: string;
  version: string;
  embedding_model: string;
  institutional_index_status: string;
  institutional_document_count: number;
  institutional_chunk_count: number;
  active_sessions: number;
};

export type SessionCreateResponse = {
  session_id: string;
};

export type UploadResponse = {
  success: boolean;
  session_id: string;
  document_name: string;
  chunk_count: number;
  message: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
    "http://127.0.0.1:8000"
  );
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) =>
          typeof item === "object" && item && "msg" in item
            ? String((item as { msg: string }).msg)
            : JSON.stringify(item),
        )
        .join("; ");
    }
    return JSON.stringify(data);
  } catch {
    return response.statusText || "Request failed";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getBaseUrl();
  const url = `${base}${path}`;
  const headers = new Headers(init?.headers);
  const clientId = getClientId();
  if (clientId) {
    headers.set("X-Client-Id", clientId);
  }
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${base}. ` +
        "Start the backend, or set NEXT_PUBLIC_API_BASE_URL to your Railway URL " +
        "(then restart / redeploy the frontend).",
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function listConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/conversations");
}

export async function createConversation(
  title = "New chat",
): Promise<ConversationDetail> {
  return request<ConversationDetail>("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function getConversation(
  conversationId: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/conversations/${encodeURIComponent(conversationId)}`,
  );
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await request(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
}

export async function clearConversation(
  conversationId: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/conversations/${encodeURIComponent(conversationId)}/clear`,
    { method: "POST" },
  );
}

function chatRequestBody(input: {
  message: string;
  conversationId?: string | null;
  sessionId?: string | null;
}): Record<string, string | null> {
  const body: Record<string, string | null> = {
    message: input.message,
    conversation_id: input.conversationId || null,
    session_id: input.sessionId || null,
  };
  const geminiKey = getGeminiApiKey();
  if (geminiKey) {
    body.api_key = geminiKey;
  }
  return body;
}

export async function sendChatMessage(input: {
  message: string;
  conversationId?: string | null;
  sessionId?: string | null;
}): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(chatRequestBody(input)),
  });
}

export type StreamChatHandlers = {
  onStart?: (payload: {
    conversation_id: string;
    user_message: ChatMessage;
    assistant_message_id: string;
    history_messages_used?: number;
    conversation_context_length?: number;
  }) => void;
  onToken?: (delta: string) => void;
  onDone?: (response: ChatResponse) => void;
  onError?: (detail: string, statusCode?: number) => void;
};

/**
 * Progressive chat via Server-Sent Events (`POST /chat/stream`).
 * Falls back to non-streaming `/chat` if the stream endpoint is unavailable.
 */
export async function streamChatMessage(
  input: {
    message: string;
    conversationId?: string | null;
    sessionId?: string | null;
    signal?: AbortSignal;
  },
  handlers: StreamChatHandlers,
): Promise<ChatResponse> {
  const url = `${getBaseUrl()}/chat/stream`;
  let response: Response;
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    const clientId = getClientId();
    if (clientId) {
      headers["X-Client-Id"] = clientId;
    }
    response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(chatRequestBody(input)),
      signal: input.signal,
    });
  } catch {
    // Network failure — try classic endpoint.
    try {
      const fallback = await sendChatMessage(input);
      handlers.onDone?.(fallback);
      return fallback;
    } catch {
      throw new ApiError(
        `Cannot reach the API at ${getBaseUrl()}. ` +
          "Start the backend, or set NEXT_PUBLIC_API_BASE_URL to your Railway URL " +
          "(then restart / redeploy the frontend).",
        0,
      );
    }
  }

  if (!response.ok || !response.body) {
    // Older backends may not expose /chat/stream yet.
    if (response.status === 404 || response.status === 405) {
      const fallback = await sendChatMessage(input);
      handlers.onDone?.(fallback);
      return fallback;
    }
    throw new ApiError(await parseError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: ChatResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const raw = trimmed.slice(5).trim();
        if (!raw || raw === "[DONE]") continue;
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(raw) as Record<string, unknown>;
        } catch {
          continue;
        }
        const event = payload.event;
        if (event === "start") {
          handlers.onStart?.({
            conversation_id: String(payload.conversation_id || ""),
            user_message: payload.user_message as ChatMessage,
            assistant_message_id: String(payload.assistant_message_id || ""),
            history_messages_used:
              typeof payload.history_messages_used === "number"
                ? payload.history_messages_used
                : undefined,
            conversation_context_length:
              typeof payload.conversation_context_length === "number"
                ? payload.conversation_context_length
                : undefined,
          });
        } else if (event === "token") {
          const delta = typeof payload.delta === "string" ? payload.delta : "";
          if (delta) handlers.onToken?.(delta);
        } else if (event === "done") {
          finalResponse = {
            conversation_id: String(payload.conversation_id || ""),
            user_message: payload.user_message as ChatMessage,
            assistant_message: payload.assistant_message as ChatMessage,
            mode: String(payload.mode || "generated"),
            streaming_supported: true,
            metadata: (payload.metadata as Record<string, unknown>) || {},
            content: typeof payload.content === "string" ? payload.content : undefined,
            status: typeof payload.status === "string" ? payload.status : undefined,
            source:
              typeof payload.source === "string" || payload.source === null
                ? (payload.source as string | null)
                : undefined,
          };
          handlers.onDone?.(finalResponse);
        } else if (event === "error") {
          const detail =
            typeof payload.detail === "string"
              ? payload.detail
              : "Streaming failed";
          const statusCode =
            typeof payload.status_code === "number"
              ? payload.status_code
              : undefined;
          handlers.onError?.(detail, statusCode);
          throw new ApiError(detail, statusCode || 500);
        }
      }
    }
  }

  if (!finalResponse) {
    throw new ApiError("Stream ended without a completed response", 500);
  }
  return finalResponse;
}

export type FollowUpChip = {
  id: string;
  label: string;
  prompt: string;
  source?: string;
};

export function extractFollowUps(
  meta?: Record<string, unknown> | null,
): FollowUpChip[] {
  if (!meta) return [];
  const raw = meta.follow_ups || meta.suggested_followups;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (item): item is FollowUpChip =>
        !!item &&
        typeof item === "object" &&
        typeof (item as FollowUpChip).label === "string" &&
        typeof (item as FollowUpChip).prompt === "string",
    )
    .map((item, idx) => ({
      id: item.id || `fu-${idx}`,
      label: item.label,
      prompt: item.prompt,
      source: item.source,
    }));
}

export async function createSession(): Promise<SessionCreateResponse> {
  return request<SessionCreateResponse>("/session", { method: "POST" });
}

export async function clearSession(sessionId: string): Promise<void> {
  await request(`/session/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export async function uploadDocument(
  sessionId: string,
  file: File,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);
  return request<UploadResponse>("/upload", {
    method: "POST",
    body: form,
  });
}

export type LLMProviderMode = "auto" | "gemini" | "lmstudio";

export type LLMSettings = {
  provider: LLMProviderMode;
  gemini_model: string;
  lmstudio_base_url: string;
  lmstudio_model: string;
  temperature: number;
  max_tokens: number;
  max_context_chunks: number;
  max_context_characters: number;
  has_google_api_key: boolean;
  gemini_server_fallback_enabled?: boolean;
  has_lmstudio_auth?: boolean;
};

export type ProviderTestResult = {
  provider: string;
  status: string;
  detail: string;
  model?: string | null;
  available_models?: string[];
};

export type ProviderHealthStatus = {
  provider_mode: string;
  lmstudio: {
    status: "online" | "offline" | string;
    detail?: string | null;
    model?: string | null;
    endpoint?: string | null;
    available_models?: string[];
  };
  gemini_server_fallback: boolean;
};

export type GeminiValidateResult = {
  valid: boolean;
  status: string;
  detail: string;
  model?: string | null;
};

export async function getLLMSettings(): Promise<LLMSettings> {
  return request<LLMSettings>("/settings/llm");
}

export async function updateLLMSettings(
  patch: Partial<
    Omit<
      LLMSettings,
      "has_google_api_key" | "gemini_server_fallback_enabled" | "has_lmstudio_auth"
    >
  >,
): Promise<LLMSettings> {
  return request<LLMSettings>("/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export async function getLLMHealth(): Promise<ProviderHealthStatus> {
  // Prefer cached provider status (background health monitor).
  // Fall back to the legacy settings health route for older backends.
  try {
    return await request<ProviderHealthStatus>("/api/providers/status");
  } catch {
    return request<ProviderHealthStatus>("/settings/llm/health");
  }
}

export async function validateGeminiApiKey(
  apiKey: string,
): Promise<GeminiValidateResult> {
  return request<GeminiValidateResult>("/settings/llm/validate-gemini", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function testLLMProvider(
  provider: "gemini" | "lmstudio",
  apiKey?: string | null,
): Promise<ProviderTestResult> {
  const body: Record<string, string> = { provider };
  if (apiKey) body.api_key = apiKey;
  return request<ProviderTestResult>("/settings/llm/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
