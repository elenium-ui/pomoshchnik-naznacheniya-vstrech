import type {
  AuthSessionResponse,
  BookingSlotsResponse,
  ClientBookingActionResponse,
  ClientBookingsListResponse,
  ClientProfileResponse,
  ClientRescheduleStartResponse,
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

export async function loadClientActiveBookings(initData: string): Promise<ClientBookingsListResponse> {
  const params = new URLSearchParams({ init_data: initData });
  const response = await fetch(`${API_BASE_URL}/api/miniapp/client/bookings/active?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load active bookings.");
  }
  return (await response.json()) as ClientBookingsListResponse;
}

export async function loadClientHistoryBookings(initData: string): Promise<ClientBookingsListResponse> {
  const params = new URLSearchParams({ init_data: initData });
  const response = await fetch(`${API_BASE_URL}/api/miniapp/client/bookings/history?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load history.");
  }
  return (await response.json()) as ClientBookingsListResponse;
}

export function cancelClientBooking(
  bookingId: number,
  initData: string
): Promise<ClientBookingActionResponse> {
  return postJson<ClientBookingActionResponse>(`/api/miniapp/client/bookings/${bookingId}/cancel`, {
    init_data: initData
  });
}

export function startClientReschedule(
  bookingId: number,
  initData: string
): Promise<ClientRescheduleStartResponse> {
  return postJson<ClientRescheduleStartResponse>(`/api/miniapp/client/bookings/${bookingId}/reschedule/start`, {
    init_data: initData
  });
}

export async function loadClientProfile(initData: string): Promise<ClientProfileResponse> {
  const params = new URLSearchParams({ init_data: initData });
  const response = await fetch(`${API_BASE_URL}/api/miniapp/client/profile?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load profile.");
  }
  return (await response.json()) as ClientProfileResponse;
}

export function updateClientProfile(payload: {
  init_data: string;
  name?: string;
  email?: string;
  phone?: string;
  reminder_enabled?: boolean | null;
}): Promise<ClientProfileResponse> {
  return postJson<ClientProfileResponse>("/api/miniapp/client/profile", payload);
}
