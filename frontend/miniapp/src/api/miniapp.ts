import type {
  AdminAvailabilitySettingsResponse,
  AdminBookingActionResponse,
  AdminBookingItem,
  AdminBookingsListResponse,
  AdminCalendarOverviewResponse,
  AdminSettingsMessageResponse,
  AuthSessionResponse,
  BookingSlotsResponse,
  ClientBookingActionResponse,
  ClientBookingsListResponse,
  ClientProfileResponse,
  ClientRescheduleStartResponse,
  JoinWaitlistResponse,
  ModeName,
  SaveBookingDraftRequest,
  SaveBookingDraftResponse,
  StartBookingSessionResponse,
  SubmittedBookingPayload
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

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

async function putJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
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

export function startBookingSession(
  initData: string,
  options?: { start_over?: boolean }
): Promise<StartBookingSessionResponse> {
  return postJson<StartBookingSessionResponse>("/api/miniapp/bookings/new/session", {
    init_data: initData,
    start_over: Boolean(options?.start_over)
  });
}

export function discardActiveDraft(initData: string): Promise<SaveBookingDraftResponse> {
  return postJson<SaveBookingDraftResponse>("/api/miniapp/bookings/draft/discard", {
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

export function joinBookingWaitlist(
  bookingId: number,
  initData: string,
  waitlistDate: string,
  waitlistComment?: string
): Promise<JoinWaitlistResponse> {
  const payload = {
    init_data: initData,
    waitlist_date: waitlistDate,
    waitlist_comment: waitlistComment ?? null
  };
  return postJson<JoinWaitlistResponse>(`/api/miniapp/bookings/${bookingId}/waitlist`, payload).catch(
    async (error: Error) => {
      if (!/not found/i.test(error.message)) {
        throw error;
      }
      // Backward-compatible fallback for environments with older booking-flow routing.
      const fallback = await postJson<ClientBookingActionResponse>(
        `/api/miniapp/client/bookings/${bookingId}/waitlist`,
        payload
      );
      return {
        booking_id: fallback.booking_id,
        status: fallback.status,
        waitlist_date: waitlistDate,
        message: fallback.message
      };
    }
  );
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

export function submitClientReschedule(
  bookingId: number,
  initData: string,
  slotKey: string
): Promise<ClientBookingActionResponse> {
  return postJson<ClientBookingActionResponse>(`/api/miniapp/client/bookings/${bookingId}/reschedule/submit`, {
    init_data: initData,
    slot_key: slotKey
  });
}

export function acceptClientWaitlistOffer(
  bookingId: number,
  initData: string
): Promise<ClientBookingActionResponse> {
  return postJson<ClientBookingActionResponse>(`/api/miniapp/client/bookings/${bookingId}/waitlist/accept`, {
    init_data: initData
  });
}

export function rejectClientWaitlistOffer(
  bookingId: number,
  initData: string
): Promise<ClientBookingActionResponse> {
  return postJson<ClientBookingActionResponse>(`/api/miniapp/client/bookings/${bookingId}/waitlist/reject`, {
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
  return putJson<ClientProfileResponse>("/api/miniapp/client/profile", payload);
}

export async function loadAdminBookings(params: {
  initData: string;
  statusFilter?: string;
  dateFilter?: string;
  search?: string;
}): Promise<AdminBookingsListResponse> {
  const query = new URLSearchParams({ init_data: params.initData });
  if (params.statusFilter) {
    query.set("status_filter", params.statusFilter);
  }
  if (params.dateFilter) {
    query.set("date_filter", params.dateFilter);
  }
  if (params.search) {
    query.set("search", params.search);
  }
  const response = await fetch(`${API_BASE_URL}/api/miniapp/admin/bookings?${query.toString()}`);
  if (!response.ok) {
    let detail = "Failed to load admin bookings.";
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      detail = "Failed to load admin bookings.";
    }
    throw new Error(detail);
  }
  return (await response.json()) as AdminBookingsListResponse;
}

export async function loadAdminBooking(initData: string, bookingId: number): Promise<AdminBookingItem> {
  const query = new URLSearchParams({ init_data: initData });
  const response = await fetch(`${API_BASE_URL}/api/miniapp/admin/bookings/${bookingId}?${query.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load booking card.");
  }
  return (await response.json()) as AdminBookingItem;
}

export function confirmAdminBooking(
  initData: string,
  bookingId: number,
  payload?: {
    admin_public_comment?: string;
    meeting_link?: string;
  }
): Promise<AdminBookingActionResponse> {
  return postJson<AdminBookingActionResponse>(`/api/miniapp/admin/bookings/${bookingId}/confirm`, {
    init_data: initData,
    ...payload
  });
}

export function rejectAdminBooking(
  initData: string,
  bookingId: number,
  payload?: {
    admin_public_comment?: string;
    meeting_link?: string;
  }
): Promise<AdminBookingActionResponse> {
  return postJson<AdminBookingActionResponse>(`/api/miniapp/admin/bookings/${bookingId}/reject`, {
    init_data: initData,
    ...payload
  });
}

export function updateAdminBookingMeta(
  initData: string,
  bookingId: number,
  payload: {
    admin_public_comment?: string;
    meeting_link?: string;
  }
): Promise<AdminBookingActionResponse> {
  return postJson<AdminBookingActionResponse>(`/api/miniapp/admin/bookings/${bookingId}/meta`, {
    init_data: initData,
    ...payload
  });
}

export function offerAdminWaitlistSlot(
  initData: string,
  bookingId: number,
  slotKey: string
): Promise<AdminBookingActionResponse> {
  return postJson<AdminBookingActionResponse>(`/api/miniapp/admin/bookings/${bookingId}/waitlist/offer`, {
    init_data: initData,
    slot_key: slotKey
  });
}

export function rejectAdminWaitlist(
  initData: string,
  bookingId: number,
  adminPublicComment: string
): Promise<AdminBookingActionResponse> {
  return postJson<AdminBookingActionResponse>(`/api/miniapp/admin/bookings/${bookingId}/waitlist/reject`, {
    init_data: initData,
    admin_public_comment: adminPublicComment
  });
}

export async function loadAdminCalendarOverview(params: {
  initData: string;
  fromDate?: string;
  days?: number;
}): Promise<AdminCalendarOverviewResponse> {
  const query = new URLSearchParams({ init_data: params.initData });
  if (params.fromDate) {
    query.set("from_date", params.fromDate);
  }
  if (typeof params.days === "number") {
    query.set("days", String(params.days));
  }
  const response = await fetch(`${API_BASE_URL}/api/miniapp/admin/calendar/overview?${query.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load calendar overview.");
  }
  return (await response.json()) as AdminCalendarOverviewResponse;
}

export async function loadAdminAvailabilitySettings(params: {
  initData: string;
  fromDate?: string;
  days?: number;
}): Promise<AdminAvailabilitySettingsResponse> {
  const query = new URLSearchParams({ init_data: params.initData });
  if (params.fromDate) {
    query.set("from_date", params.fromDate);
  }
  if (typeof params.days === "number") {
    query.set("days", String(params.days));
  }
  const response = await fetch(`${API_BASE_URL}/api/miniapp/admin/availability/settings?${query.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load availability settings.");
  }
  return (await response.json()) as AdminAvailabilitySettingsResponse;
}

export function addAdminWorkingWindow(payload: {
  init_data: string;
  weekday: number;
  start_time: string;
  end_time: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/working-windows", payload);
}

export function clearAdminWorkingWindows(payload: {
  init_data: string;
  weekday?: number;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/working-windows/clear", payload);
}

export function removeAdminWorkingWindow(payload: {
  init_data: string;
  rule_id: number;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/working-windows/remove", payload);
}

export function updateAdminMinLead(payload: {
  init_data: string;
  minutes: number;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/min-lead", payload);
}

export function closeAdminDay(payload: {
  init_data: string;
  date: string;
  reason?: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/closed-days/close", payload);
}

export function reopenAdminDay(payload: {
  init_data: string;
  date: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/closed-days/reopen", payload);
}

export function addAdminTimeBlock(payload: {
  init_data: string;
  date: string;
  start_time: string;
  end_time: string;
  comment?: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/time-blocks", payload);
}

export function removeAdminTimeBlock(payload: {
  init_data: string;
  block_id: number;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/time-blocks/remove", payload);
}

export function addAdminOneTimeWindow(payload: {
  init_data: string;
  date: string;
  start_time: string;
  end_time: string;
  comment?: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>("/api/miniapp/admin/availability/one-time-windows", payload);
}

export function removeAdminOneTimeWindowsByDate(payload: {
  init_data: string;
  date: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>(
    "/api/miniapp/admin/availability/one-time-windows/remove-by-date",
    payload
  );
}

export function removeAdminOneTimeWindow(payload: {
  init_data: string;
  date: string;
  start_time: string;
  end_time: string;
}): Promise<AdminSettingsMessageResponse> {
  return postJson<AdminSettingsMessageResponse>(
    "/api/miniapp/admin/availability/one-time-windows/remove",
    payload
  );
}
