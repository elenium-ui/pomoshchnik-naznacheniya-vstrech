export type ModeName = "client" | "admin";

export type AuthSessionResponse = {
  user: {
    telegram_user_id: number;
    first_name: string | null;
    last_name: string | null;
    username: string | null;
  };
  access: {
    is_admin: boolean;
    available_modes: ModeName[];
    default_mode: ModeName;
    current_mode: ModeName;
  };
};

export type BookingProfile = {
  name: string | null;
  email: string | null;
  phone: string | null;
  telegram_username: string | null;
};

export type StartBookingSessionResponse = {
  booking_id: number;
  future_active_count: number;
  future_active_limit: number;
  profile: BookingProfile;
};

export type SaveBookingDraftRequest = {
  init_data: string;
  name: string;
  topic: string;
  meeting_format: string;
  duration_minutes: number;
  email?: string | null;
  phone?: string | null;
  comment?: string | null;
};

export type SaveBookingDraftResponse = {
  booking_id: number;
  status: string;
  duration_minutes: number;
  profile: BookingProfile;
};

export type SlotOption = {
  label: string;
  key: string;
};

export type SlotTimeOption = {
  label: string;
  slot_key: string;
  starts_at: string;
  ends_at: string;
};

export type BookingSlotsResponse = {
  total_slots: number;
  non_empty_days: number;
  week_options: SlotOption[];
  day_options_by_week: Record<string, SlotOption[]>;
  time_options_by_day: Record<string, SlotTimeOption[]>;
};

export type SubmittedBookingPayload = {
  booking_id: number;
  status: string;
  topic: string | null;
  meeting_format: string | null;
  duration_minutes: number | null;
  comment: string | null;
  slot_start_at: string;
  slot_end_at: string;
};

export type ClientBookingItem = {
  booking_id: number;
  status: string;
  topic: string | null;
  meeting_format: string | null;
  duration_minutes: number | null;
  slot_start_at: string | null;
  slot_end_at: string | null;
  comment: string | null;
  admin_public_comment: string | null;
  meeting_link: string | null;
  calendar_event_id: string | null;
  updated_at: string;
};

export type ClientBookingsListResponse = {
  items: ClientBookingItem[];
};

export type ClientBookingActionResponse = {
  booking_id: number;
  status: string;
  message: string;
};

export type ClientRescheduleStartResponse = {
  booking_id: number;
  status: string;
  duration_minutes: number;
  current_slot_start_at: string;
  current_slot_end_at: string;
  available_slots: BookingSlotsResponse;
  message: string;
};

export type ClientProfilePayload = {
  name: string | null;
  email: string | null;
  phone: string | null;
  telegram_username: string | null;
  reminder_supported: boolean;
  reminder_enabled: boolean | null;
};

export type ClientProfileResponse = {
  profile: ClientProfilePayload;
};

export type AdminBookingUser = {
  user_id: number;
  telegram_user_id: number;
  telegram_username: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
};

export type AdminBookingItem = {
  booking_id: number;
  status: string;
  topic: string | null;
  meeting_format: string | null;
  duration_minutes: number | null;
  slot_start_at: string | null;
  slot_end_at: string | null;
  requested_new_slot_start_at: string | null;
  requested_new_slot_end_at: string | null;
  comment: string | null;
  admin_public_comment: string | null;
  meeting_link: string | null;
  calendar_event_id: string | null;
  updated_at: string;
  user: AdminBookingUser;
};

export type AdminBookingsListResponse = {
  items: AdminBookingItem[];
};

export type AdminBookingActionResponse = {
  booking_id: number;
  status: string;
  message: string;
  admin_public_comment: string | null;
  meeting_link: string | null;
};

export type AdminCalendarBookingPreview = {
  booking_id: number;
  topic: string | null;
  status: string;
  slot_start_at: string;
  slot_end_at: string;
  client_name: string | null;
  client_username: string | null;
};

export type AdminCalendarDay = {
  date: string;
  is_closed: boolean;
  closed_reason: string | null;
  working_windows: Array<{
    start_time: string;
    end_time: string;
  }>;
  time_blocks: Array<{
    block_id: number;
    date: string;
    start_time: string;
    end_time: string;
    comment: string | null;
  }>;
  pending_count: number;
  confirmed_count: number;
  reschedule_count: number;
  bookings_preview: AdminCalendarBookingPreview[];
};

export type AdminCalendarOverviewResponse = {
  items: AdminCalendarDay[];
};

export type AdminAvailabilitySettingsResponse = {
  min_lead_minutes: number | null;
  working_windows: Array<{
    rule_id: number;
    weekday: number;
    start_time: string;
    end_time: string;
  }>;
  closed_days: Array<{
    date: string;
    reason: string | null;
  }>;
  time_blocks: Array<{
    block_id: number;
    date: string;
    start_time: string;
    end_time: string;
    comment: string | null;
  }>;
  one_time_windows: Array<{
    date: string;
    start_time: string;
    end_time: string;
    comment: string | null;
  }>;
};

export type AdminSettingsMessageResponse = {
  message: string;
};
