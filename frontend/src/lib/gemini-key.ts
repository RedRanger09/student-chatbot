/**
 * Browser-only Gemini API key storage.
 *
 * Never sent to analytics, cookies, or permanent server storage.
 * The key is attached to chat requests only when generating with Gemini.
 */

const STORAGE_KEY = "gemini_api_key";

export function getGeminiApiKey(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    const cleaned = (value || "").trim();
    return cleaned || null;
  } catch {
    return null;
  }
}

export function setGeminiApiKey(apiKey: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const cleaned = (apiKey || "").trim();
    if (!cleaned) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, cleaned);
  } catch {
    // Ignore quota / private-mode failures.
  }
}

export function clearGeminiApiKey(): void {
  setGeminiApiKey(null);
}

export function hasGeminiApiKey(): boolean {
  return !!getGeminiApiKey();
}
