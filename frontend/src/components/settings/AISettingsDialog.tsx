"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Loader2, Settings } from "lucide-react";
import { toast } from "sonner";
import {
  ApiError,
  getLLMHealth,
  getLLMSettings,
  testLLMProvider,
  updateLLMSettings,
  validateGeminiApiKey,
  type LLMProviderMode,
  type LLMSettings,
  type ProviderTestResult,
} from "@/lib/api";
import {
  getAIInspectorEnabled,
  setAIInspectorEnabled,
  getSourcesEnabled,
  setSourcesEnabled,
} from "@/lib/citations";
import {
  getGeminiApiKey,
  hasGeminiApiKey,
  setGeminiApiKey,
} from "@/lib/gemini-key";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

type StatusKind = "idle" | "connected" | "offline" | "missing_api_key" | "error";

function StatusBadge({
  label,
  status,
  overrideText,
}: {
  label: string;
  status: StatusKind;
  overrideText?: string;
}) {
  const map: Record<StatusKind, { emoji: string; text: string }> = {
    idle: { emoji: "⚪", text: "Not tested" },
    connected: { emoji: "🟢", text: "Online" },
    offline: { emoji: "🔴", text: "Offline" },
    missing_api_key: { emoji: "⚠", text: "No API Key" },
    error: { emoji: "🔴", text: "Error" },
  };
  const item = map[status] || map.idle;
  const text = overrideText || `${item.emoji} ${item.text}`;
  return (
    <div className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--surface-2)] px-3 py-2 text-sm">
      <span className="font-medium">{label}</span>
      <span>{text}</span>
    </div>
  );
}

function toStatus(result: ProviderTestResult | null, hasKey?: boolean): StatusKind {
  if (!result) {
    if (hasKey === false) return "missing_api_key";
    return "idle";
  }
  if (result.status === "connected") return "connected";
  if (result.status === "missing_api_key") return "missing_api_key";
  if (result.status === "offline") return "offline";
  return "error";
}

export function AISettingsDialog() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<"gemini" | "lmstudio" | null>(null);
  const [validating, setValidating] = useState(false);
  const [form, setForm] = useState<LLMSettings | null>(null);
  const [geminiTest, setGeminiTest] = useState<ProviderTestResult | null>(null);
  const [lmTest, setLmTest] = useState<ProviderTestResult | null>(null);
  const [lmOnline, setLmOnline] = useState<boolean | null>(null);
  const [aiInspector, setAiInspector] = useState(false);
  const [sourcesVisible, setSourcesVisible] = useState(true);
  const [geminiKeyDraft, setGeminiKeyDraft] = useState("");
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [geminiKeyConfigured, setGeminiKeyConfigured] = useState(false);
  const [geminiValidateOk, setGeminiValidateOk] = useState<boolean | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setAiInspector(getAIInspectorEnabled());
    setSourcesVisible(getSourcesEnabled());
    setGeminiKeyDraft(getGeminiApiKey() || "");
    setGeminiKeyConfigured(hasGeminiApiKey());
    setGeminiValidateOk(null);
    void Promise.all([getLLMSettings(), getLLMHealth().catch(() => null)])
      .then(([data, health]) => {
        if (cancelled) return;
        setForm(data);
        if (health?.lmstudio) {
          const online = health.lmstudio.status === "online";
          setLmOnline(online);
          setLmTest({
            provider: "lmstudio",
            status: online ? "connected" : "offline",
            detail: health.lmstudio.detail || "",
            model: health.lmstudio.model,
            available_models: health.lmstudio.available_models,
          });
        }
      })
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Could not load settings");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  function patch<K extends keyof LLMSettings>(key: K, value: LLMSettings[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function handleSave() {
    if (!form) return;
    setSaving(true);
    try {
      const saved = await updateLLMSettings({
        provider: form.provider,
        gemini_model: form.gemini_model,
        lmstudio_base_url: form.lmstudio_base_url,
        lmstudio_model: form.lmstudio_model,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        max_context_chunks: form.max_context_chunks,
        max_context_characters: form.max_context_characters,
      });
      setForm(saved);
      const draft = geminiKeyDraft.trim();
      if (!draft) {
        setGeminiApiKey(null);
        setGeminiKeyConfigured(false);
      } else if (geminiValidateOk === false) {
        // Do not overwrite a previous good key with an invalid draft.
        toast.message("Invalid Gemini API key was not saved");
      } else {
        setGeminiApiKey(draft);
        setGeminiKeyConfigured(true);
      }
      setAIInspectorEnabled(aiInspector);
      setSourcesEnabled(sourcesVisible);
      toast.success("AI settings saved");
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleValidateGemini() {
    const key = geminiKeyDraft.trim();
    if (!key) {
      setGeminiValidateOk(false);
      toast.error("Enter a Gemini API key first");
      return;
    }
    setValidating(true);
    try {
      const result = await validateGeminiApiKey(key);
      if (result.valid) {
        setGeminiApiKey(key);
        setGeminiKeyConfigured(true);
        setGeminiValidateOk(true);
        setGeminiTest({
          provider: "gemini",
          status: "connected",
          detail: result.detail,
          model: result.model,
        });
        toast.success("✓ Gemini API key verified");
      } else {
        setGeminiValidateOk(false);
        // Do not save invalid keys.
        toast.error("✕ Invalid API key");
      }
    } catch (err) {
      setGeminiValidateOk(false);
      toast.error(err instanceof ApiError ? err.message : "✕ Invalid API key");
    } finally {
      setValidating(false);
    }
  }

  async function handleTest(provider: "gemini" | "lmstudio") {
    setTesting(provider);
    try {
      if (form) {
        await updateLLMSettings({
          provider: form.provider,
          gemini_model: form.gemini_model,
          lmstudio_base_url: form.lmstudio_base_url,
          lmstudio_model: form.lmstudio_model,
          temperature: form.temperature,
          max_tokens: form.max_tokens,
        });
      }
      const key = provider === "gemini" ? geminiKeyDraft.trim() || getGeminiApiKey() : null;
      const result = await testLLMProvider(provider, key);
      if (provider === "gemini") setGeminiTest(result);
      else {
        setLmTest(result);
        setLmOnline(result.status === "connected");
      }
      if (result.status === "connected") {
        toast.success(`${provider === "gemini" ? "Gemini" : "LM Studio"} connected`);
      } else {
        toast.message(result.detail || "Connection check finished");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Connection test failed");
    } finally {
      setTesting(null);
    }
  }

  const providers: { id: LLMProviderMode; label: string; hint: string }[] = [
    {
      id: "auto",
      label: "Auto (Recommended)",
      hint: "Automatically selects the best available provider based on your configuration.",
    },
    { id: "gemini", label: "Gemini", hint: "Google Generative AI cloud model" },
    { id: "lmstudio", label: "LM Studio", hint: "Local OpenAI-compatible endpoint" },
  ];

  const geminiStatusText = geminiKeyConfigured
    ? "✓ API Key Configured"
    : "⚠ No API Key";
  const lmStatusText =
    lmOnline === true
      ? "🟢 Online"
      : lmOnline === false
        ? "🔴 Offline"
        : undefined;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="AI Settings">
          <Settings className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] w-[min(94vw,560px)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>AI Settings</DialogTitle>
          <DialogDescription>
            Choose how answers are generated. The assistant stays grounded in retrieved
            campus documents or your uploaded notes.
          </DialogDescription>
        </DialogHeader>

        {loading || !form ? (
          <div className="flex items-center justify-center py-10 text-[var(--muted)]">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading settings…
          </div>
        ) : (
          <div className="space-y-5">
            <section className="space-y-2">
              <p className="text-sm font-semibold">Generation Provider</p>
              <div className="space-y-2">
                {providers.map((item) => (
                  <label
                    key={item.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                      form.provider === item.id
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--line)] hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="provider"
                      className="mt-1"
                      checked={form.provider === item.id}
                      onChange={() => patch("provider", item.id)}
                    />
                    <span>
                      <span className="block text-sm font-medium">{item.label}</span>
                      <span className="block text-xs text-[var(--muted)]">{item.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <Separator />

            <section className="space-y-2">
              <label className="text-sm font-semibold" htmlFor="gemini-model">
                Gemini Model
              </label>
              <Input
                id="gemini-model"
                value={form.gemini_model}
                onChange={(e) => patch("gemini_model", e.target.value)}
                placeholder="gemini-2.5-flash"
              />
            </section>

            {form.provider === "gemini" || form.provider === "auto" ? (
              <section className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface-2)] p-3">
                <label className="text-sm font-semibold" htmlFor="gemini-api-key">
                  Gemini API Key
                </label>
                <div className="flex gap-2">
                  <Input
                    id="gemini-api-key"
                    type={showGeminiKey ? "text" : "password"}
                    value={geminiKeyDraft}
                    onChange={(e) => {
                      setGeminiKeyDraft(e.target.value);
                      setGeminiValidateOk(null);
                    }}
                    placeholder="AIzaSy..."
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label={showGeminiKey ? "Hide API key" : "Show API key"}
                    onClick={() => setShowGeminiKey((v) => !v)}
                  >
                    {showGeminiKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={validating}
                    onClick={() => void handleValidateGemini()}
                  >
                    {validating ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : null}
                    Validate
                  </Button>
                  {geminiValidateOk === true ? (
                    <span className="text-xs text-emerald-600 dark:text-emerald-400">
                      ✓ Gemini API key verified
                    </span>
                  ) : null}
                  {geminiValidateOk === false ? (
                    <span className="text-xs text-red-600 dark:text-red-400">
                      ✕ Invalid API key
                    </span>
                  ) : null}
                </div>
                <ul className="space-y-0.5 text-xs text-[var(--muted)]">
                  <li>• Stored only in this browser.</li>
                  <li>• Never stored on the server.</li>
                  <li>• Used only when generating Gemini responses.</li>
                </ul>
              </section>
            ) : null}

            <section className="space-y-2">
              <label className="text-sm font-semibold" htmlFor="lm-endpoint">
                LM Studio Endpoint
              </label>
              <Input
                id="lm-endpoint"
                value={form.lmstudio_base_url}
                onChange={(e) => patch("lmstudio_base_url", e.target.value)}
                placeholder="https://your-tunnel-domain/v1"
              />
              <p className="text-xs text-[var(--muted)]">
                Any OpenAI-compatible base URL (LM Studio, Ollama, vLLM, LocalAI, or a
                secure tunnel). Do not assume localhost in production.
              </p>
            </section>

            <section className="space-y-2">
              <label className="text-sm font-semibold" htmlFor="lm-model">
                LM Studio Model
              </label>
              <Input
                id="lm-model"
                value={form.lmstudio_model}
                onChange={(e) => patch("lmstudio_model", e.target.value)}
                placeholder="auto"
              />
              <p className="text-xs text-[var(--muted)]">
                Use <span className="font-medium">auto</span> to pick whatever model is
                currently loaded. You can still set a specific name if you prefer.
              </p>
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold">Temperature</span>
                <span className="tabular-nums text-[var(--muted)]">
                  {form.temperature.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={1.5}
                step={0.05}
                value={form.temperature}
                onChange={(e) => patch("temperature", Number(e.target.value))}
                className="w-full accent-[var(--accent)]"
              />
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold">Maximum Tokens</span>
                <span className="tabular-nums text-[var(--muted)]">{form.max_tokens}</span>
              </div>
              <input
                type="range"
                min={64}
                max={4096}
                step={64}
                value={form.max_tokens}
                onChange={(e) => patch("max_tokens", Number(e.target.value))}
                className="w-full accent-[var(--accent)]"
              />
            </section>

            <Separator />

            <section className="space-y-2">
              <p className="text-sm font-semibold">Sources</p>
              <p className="text-xs text-[var(--muted)]">
                When ON, grounded replies show the documents used to answer. When
                OFF, the chat stays clear without a Sources panel.
              </p>
              <div className="space-y-2">
                {[
                  {
                    id: true,
                    label: "ON (Default)",
                    hint: "Show Sources under grounded answers",
                  },
                  {
                    id: false,
                    label: "OFF",
                    hint: "Hide Sources — keep the chat clean",
                  },
                ].map((item) => (
                  <label
                    key={String(item.id)}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                      sourcesVisible === item.id
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--line)] hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="sources-visible"
                      className="mt-1"
                      checked={sourcesVisible === item.id}
                      onChange={() => setSourcesVisible(item.id)}
                    />
                    <span>
                      <span className="block text-sm font-medium">{item.label}</span>
                      <span className="block text-xs text-[var(--muted)]">{item.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <Separator />

            <section className="space-y-2">
              <p className="text-sm font-semibold">AI Inspector</p>
              <p className="text-xs text-[var(--muted)]">
                Developer mode. When ON, a collapsed debugging panel appears under
                each assistant reply. Normal chat stays clean when OFF.
              </p>
              <div className="space-y-2">
                {[
                  {
                    id: false,
                    label: "OFF (Default)",
                    hint: "Hide debugging panel under replies",
                  },
                  {
                    id: true,
                    label: "ON",
                    hint: "Show expandable AI Inspector under replies",
                  },
                ].map((item) => (
                  <label
                    key={String(item.id)}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                      aiInspector === item.id
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--line)] hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="ai-inspector"
                      className="mt-1"
                      checked={aiInspector === item.id}
                      onChange={() => setAiInspector(item.id)}
                    />
                    <span>
                      <span className="block text-sm font-medium">{item.label}</span>
                      <span className="block text-xs text-[var(--muted)]">{item.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <Separator />

            <section className="space-y-2">
              <p className="text-sm font-semibold">Provider status</p>
              <StatusBadge
                label="Gemini"
                status={
                  geminiKeyConfigured
                    ? "connected"
                    : toStatus(geminiTest, false)
                }
                overrideText={geminiStatusText}
              />
              <StatusBadge
                label="LM Studio"
                status={toStatus(lmTest)}
                overrideText={lmStatusText}
              />
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={testing !== null}
                  onClick={() => void handleTest("gemini")}
                >
                  {testing === "gemini" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Test Gemini
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={testing !== null}
                  onClick={() => void handleTest("lmstudio")}
                >
                  {testing === "lmstudio" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Test LM Studio
                </Button>
              </div>
            </section>

            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="button" onClick={() => void handleSave()} disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Save
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
