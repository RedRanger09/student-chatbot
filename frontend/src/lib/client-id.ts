/**
 * Stable per-browser client id for conversation ownership.
 * Stored only in localStorage — never sent to other users.
 */

const CLIENT_ID_KEY = "ssc_client_id";

function createId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `ssc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function getClientId(): string {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    const existing = window.localStorage.getItem(CLIENT_ID_KEY)?.trim();
    if (existing) {
      return existing;
    }
    const created = createId();
    window.localStorage.setItem(CLIENT_ID_KEY, created);
    return created;
  } catch {
    // Private mode / blocked storage — ephemeral id for this page load.
    return createId();
  }
}
