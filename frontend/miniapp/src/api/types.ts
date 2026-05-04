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
