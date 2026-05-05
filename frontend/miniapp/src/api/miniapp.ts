import type {
  AuthSessionResponse,
  BookingSlotsResponse,
  ModeName,
  SaveBookingDraftRequest,
  SaveBookingDraftResponse,
  StartBookingSessionResponse,
  SubmittedBookingPayload
} from "./types";

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

export function startBookingSession(initData: string): Promise<StartBookingSessionResponse> {
  return postJson<StartBookingSessionResponse>("/api/miniapp/bookings/new/session", {
    init_data: initData
  });
}

export function saveBookingDraft(
  bookingId: number,
  payload: SaveBookingDraftRequest
): Promise<SaveBookingDraftResponse> {
  // Use POST for broader compatibility in local/dev gateways that can block PUT.
  return postJson<SaveBookingDraftResponse>(`/api/miniapp/bookings/${bookingId}/details`, payload);
}

export async function loadBookingSlots(
  initData: string,
  durationMinutes: number
): Promise<BookingSlotsResponse> {
  const params = new URLSearchParams({
    init_data: initData,
    duration_minutes: String(durationMinutes)
  });
  const response = await fetch(`${API_BASE_URL}/api/miniapp/bookings/slots?${params.toString()}`);
  if (!response.ok) {
    let detail = "Failed to load slots.";
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      detail = "Failed to load slots.";
    }
    throw new Error(detail);
  }
  return (await response.json()) as BookingSlotsResponse;
}

export function submitBooking(
  bookingId: number,
  initData: string,
  slotKey: string
): Promise<SubmittedBookingPayload> {
  return postJson<SubmittedBookingPayload>(`/api/miniapp/bookings/${bookingId}/submit`, {
    init_data: initData,
    slot_key: slotKey
  });
}
