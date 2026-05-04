import type { AuthSessionResponse, ModeName } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8090";

type ApiErrorPayload = {
  detail?: string;
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    let detail = "API request failed.";
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      detail = "API request failed.";
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function createAuthSession(initData: string): Promise<AuthSessionResponse> {
  return postJson<AuthSessionResponse>("/api/miniapp/auth/session", {
    init_data: initData
  });
}

export function switchAuthMode(initData: string, mode: ModeName): Promise<AuthSessionResponse> {
  return postJson<AuthSessionResponse>("/api/miniapp/auth/mode", {
    init_data: initData,
    mode
  });
}

