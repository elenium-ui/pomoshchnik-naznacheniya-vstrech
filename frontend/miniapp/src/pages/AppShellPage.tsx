import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addAdminOneTimeWindow,
  addAdminTimeBlock,
  addAdminWorkingWindow,
  cancelClientBooking,
  clearAdminWorkingWindows,
  closeAdminDay,
  confirmAdminBooking,
  createAuthSession,
  loadAdminAvailabilitySettings,
  loadAdminBooking,
  loadAdminBookings,
  loadAdminCalendarOverview,
  loadClientActiveBookings,
  loadClientHistoryBookings,
  loadClientProfile,
  rejectAdminBooking,
  removeAdminWorkingWindow,
  removeAdminTimeBlock,
  removeAdminOneTimeWindow,
  removeAdminOneTimeWindowsByDate,
  reopenAdminDay,
  startClientReschedule,
  submitClientReschedule,
  switchAuthMode,
  updateAdminMinLead,
  updateClientProfile
} from "../api/miniapp";
import type {
  AdminBookingItem,
  AdminCalendarDay,
  AuthSessionResponse,
  BookingSlotsResponse,
  ClientBookingItem,
  ModeName,
  SlotTimeOption
} from "../api/types";
import { NewBookingFlow } from "../features/new-booking/NewBookingFlow";
import { getTelegramInitData, getTelegramWebApp } from "../telegram/webapp";
import styles from "./AppShellPage.module.scss";

type NavItem = {
  key: string;
  title: string;
  subtitle: string;
};

const clientNav: NavItem[] = [
  { key: "home", title: "Главная", subtitle: "Запись на встречу с Еленой" },
  { key: "bookings", title: "Мои заявки", subtitle: "Текущие заявки и их статусы" },
  { key: "history", title: "История", subtitle: "Завершенные встречи" },
  { key: "profile", title: "Профиль", subtitle: "Контакты и режим приложения" }
];

const adminNav: NavItem[] = [
  { key: "requests", title: "Заявки", subtitle: "Список входящих заявок" },
  { key: "calendar", title: "Календарь", subtitle: "Загрузка по дням" },
  { key: "settings", title: "Настройки", subtitle: "Доступность и правила записи" },
  { key: "profile", title: "Профиль", subtitle: "Режим и личные данные" }
];

function getFirstName(payload: AuthSessionResponse): string {
  return payload.user.first_name ?? payload.user.username ?? "друг";
}

function formatSlot(startAt: string | null, endAt: string | null): string {
  if (!startAt || !endAt) {
    return "Слот ещё не выбран";
  }
  const start = new Date(startAt);
  const end = new Date(endAt);
  const dateLabel = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    weekday: "long",
  }).format(start);
  const timeLabel = `${start.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} - ${end.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit"
  })}`;
  return `${dateLabel}, ${timeLabel}`;
}

function formatTimeRange(startAt: string | null, endAt: string | null): string {
  if (!startAt || !endAt) {
    return "Время не выбрано";
  }
  const start = new Date(startAt);
  const end = new Date(endAt);
  return `${start.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} - ${end.toLocaleTimeString(
    "ru-RU",
    {
      hour: "2-digit",
      minute: "2-digit"
    }
  )}`;
}

function statusLabel(status: string): string {
  const mapping: Record<string, string> = {
    draft: "Черновик",
    pending_decision: "Ожидает решения",
    confirmed: "Подтверждена",
    reschedule_requested: "Запрошен перенос",
    rejected: "Отклонена",
    expired: "Истекла",
    canceled_by_user: "Отменена вами",
    canceled_by_admin: "Отменена администратором",
    cancelled_by_user: "Отменена вами",
    cancelled_by_admin: "Отменена администратором"
  };
  return mapping[status] ?? "В обработке";
}

function statusLabelForCard(status: string, slotEndAt: string | null): string {
  if (status === "confirmed" && slotEndAt && new Date(slotEndAt).getTime() < Date.now()) {
    return "Завершена";
  }
  return statusLabel(status);
}

function statusBadgeClass(status: string): string {
  if (status === "confirmed") {
    return styles.statusBadgeSuccess;
  }
  if (status === "pending_decision" || status === "reschedule_requested") {
    return styles.statusBadgeWarning;
  }
  if (
    status === "rejected" ||
    status === "expired" ||
    status === "canceled_by_user" ||
    status === "canceled_by_admin" ||
    status === "cancelled_by_user" ||
    status === "cancelled_by_admin"
  ) {
    return styles.statusBadgeDanger;
  }
  return styles.statusBadgeNeutral;
}

function formatTelegramUsername(username: string | null): string {
  if (!username) {
    return "—";
  }
  return username.startsWith("@") ? username : `@${username}`;
}

function formatAdminClientName(user: AdminBookingItem["user"]): string {
  return user.name || user.telegram_username || `ID ${user.telegram_user_id}`;
}

type RescheduleState = {
  bookingId: number;
  topic: string;
  currentSlotLabel: string;
  slotsData: BookingSlotsResponse;
  selectedWeek: string;
  selectedDay: string;
  selectedSlot: SlotTimeOption | null;
};

type CancelDialogState = {
  bookingId: number;
  topic: string;
  comment: string;
  error: string;
};

type AdminQuickView = "needs_action" | "confirmed" | "canceled" | "archive" | "all";
type ClientQuickFilter = "all" | "pending" | "confirmed" | "draft" | "canceled";
type AdminSettingsSection = "lead" | "windows" | "one_time" | "closed_days" | "time_blocks";

const ADMIN_ARCHIVE_STATUSES = new Set([
  "rejected",
  "expired",
  "canceled_by_user",
  "canceled_by_admin",
  "cancelled_by_user",
  "cancelled_by_admin"
]);

const CLIENT_FILTER_STATUS_MAP: Record<Exclude<ClientQuickFilter, "all">, Set<string>> = {
  pending: new Set(["pending_decision", "reschedule_requested"]),
  confirmed: new Set(["confirmed"]),
  draft: new Set(["draft"]),
  canceled: new Set([
    "rejected",
    "expired",
    "canceled_by_user",
    "canceled_by_admin",
    "cancelled_by_user",
    "cancelled_by_admin"
  ])
};

const CLIENT_BOOKING_PRIORITY: Record<string, number> = {
  pending_decision: 0,
  reschedule_requested: 0,
  confirmed: 1,
  draft: 2,
  rejected: 3,
  expired: 3,
  canceled_by_user: 3,
  canceled_by_admin: 3,
  cancelled_by_user: 3,
  cancelled_by_admin: 3
};

function formatWeekLabel(weekKey: string): string {
  const start = new Date(weekKey);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const startLabel = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(start);
  const endLabel = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(end);
  if (start.getFullYear() === end.getFullYear()) {
    return `Неделя ${startLabel} - ${endLabel} ${start.getFullYear()} года`;
  }
  return `Неделя ${startLabel} ${start.getFullYear()} - ${endLabel} ${end.getFullYear()}`;
}

function toIsoDate(dateValue: Date): string {
  const year = dateValue.getFullYear();
  const month = String(dateValue.getMonth() + 1).padStart(2, "0");
  const day = String(dateValue.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseIsoDate(dateValue: string): Date {
  const [year, month, day] = dateValue.split("-").map((item) => Number(item));
  if (!year || !month || !day) {
    return new Date(dateValue);
  }
  return new Date(year, month - 1, day, 0, 0, 0, 0);
}

function formatDayLabel(dateValue: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    weekday: "long"
  }).format(parseIsoDate(dateValue));
}

function weekdayLabel(weekday: number): string {
  const labels = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
  return labels[weekday] ?? String(weekday);
}

function startOfWeek(dateValue: Date): Date {
  const result = new Date(dateValue);
  const day = result.getDay();
  const deltaToMonday = day === 0 ? -6 : 1 - day;
  result.setDate(result.getDate() + deltaToMonday);
  result.setHours(0, 0, 0, 0);
  return result;
}

function endOfWeek(dateValue: Date): Date {
  const start = startOfWeek(dateValue);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return end;
}

function addDays(dateValue: Date, days: number): Date {
  const result = new Date(dateValue);
  result.setDate(result.getDate() + days);
  return result;
}

function diffDaysInclusive(start: Date, end: Date): number {
  const msPerDay = 24 * 60 * 60 * 1000;
  const startMs = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate());
  const endMs = Date.UTC(end.getFullYear(), end.getMonth(), end.getDate());
  return Math.floor((endMs - startMs) / msPerDay) + 1;
}

export function AppShellPage() {
  const initData = useMemo(() => getTelegramInitData(), []);
  const hostPhotoUrl = (import.meta.env.VITE_HOST_PHOTO_URL ?? "/host-photo.png").trim();
  const todayIso = useMemo(() => toIsoDate(new Date()), []);
  const queryClient = useQueryClient();
  const [currentMode, setCurrentMode] = useState<ModeName | null>(null);
  const [activeTabKey, setActiveTabKey] = useState<string>("home");
  const [newBookingOpen, setNewBookingOpen] = useState(false);
  const [actionMessage, setActionMessage] = useState<string>("");
  const [rescheduleError, setRescheduleError] = useState<string>("");
  const [rescheduleState, setRescheduleState] = useState<RescheduleState | null>(null);
  const [cancelDialog, setCancelDialog] = useState<CancelDialogState | null>(null);
  const [profileForm, setProfileForm] = useState({
    name: "",
    email: "",
    phone: ""
  });
  const [selectedAdminBookingId, setSelectedAdminBookingId] = useState<number | null>(null);
  const [adminMetaForm, setAdminMetaForm] = useState({
    admin_public_comment: "",
    meeting_link: ""
  });
  const [adminQuickView, setAdminQuickView] = useState<AdminQuickView>("needs_action");
  const [clientQuickFilter, setClientQuickFilter] = useState<ClientQuickFilter>("all");
  const [photoLoadFailed, setPhotoLoadFailed] = useState(false);
  const [calendarFromDate, setCalendarFromDate] = useState(todayIso);
  const [calendarUseCurrentWeek, setCalendarUseCurrentWeek] = useState(true);
  const [minLeadMinutesInput, setMinLeadMinutesInput] = useState("60");
  const [workingWindowForm, setWorkingWindowForm] = useState({
    weekday: "0",
    start_time: "10:00",
    end_time: "12:00"
  });
  const [workingWindowFeedback, setWorkingWindowFeedback] = useState("");
  const [closedDayForm, setClosedDayForm] = useState({
    date: todayIso,
    reason: ""
  });
  const [timeBlockForm, setTimeBlockForm] = useState({
    date: todayIso,
    start_time: "12:00",
    end_time: "13:00",
    comment: ""
  });
  const [oneTimeWindowForm, setOneTimeWindowForm] = useState({
    date: todayIso,
    start_time: "10:00",
    end_time: "12:00",
    comment: ""
  });
  const [openAdminSection, setOpenAdminSection] = useState<AdminSettingsSection | null>(null);

  useEffect(() => {
    const webApp = getTelegramWebApp();
    webApp?.ready();
    webApp?.expand();
  }, []);

  const sessionQuery = useQuery({
    queryKey: ["miniapp-auth-session", initData],
    queryFn: () => createAuthSession(initData),
    enabled: initData.length > 0,
    retry: false
  });

  useEffect(() => {
    if (!sessionQuery.data) {
      return;
    }
    setCurrentMode(sessionQuery.data.access.current_mode);
  }, [sessionQuery.data]);

  const modeSwitchMutation = useMutation({
    mutationFn: (mode: ModeName) => switchAuthMode(initData, mode),
    onSuccess: (payload) => {
      setCurrentMode(payload.access.current_mode);
    }
  });

  const resolvedMode = currentMode ?? sessionQuery.data?.access.default_mode ?? null;
  const navItems = resolvedMode === "admin" ? adminNav : clientNav;
  const calendarQueryDays = useMemo(() => {
    if (!calendarUseCurrentWeek) {
      return 7;
    }
    const now = new Date();
    return diffDaysInclusive(now, endOfWeek(now));
  }, [calendarUseCurrentWeek]);
  const calendarRangeStart = useMemo(
    () => (calendarUseCurrentWeek ? todayIso : calendarFromDate),
    [calendarUseCurrentWeek, todayIso, calendarFromDate]
  );
  const calendarRangeLabel = useMemo(() => {
    const start = parseIsoDate(calendarRangeStart);
    const end = addDays(start, calendarQueryDays - 1);
    return `${formatDayLabel(toIsoDate(start))} - ${formatDayLabel(toIsoDate(end))}`;
  }, [calendarRangeStart, calendarQueryDays]);

  const activeBookingsQuery = useQuery({
    queryKey: ["miniapp-client-active-bookings", initData],
    queryFn: () => loadClientActiveBookings(initData),
    enabled: Boolean(initData) && resolvedMode === "client" && activeTabKey === "bookings"
  });

  const historyBookingsQuery = useQuery({
    queryKey: ["miniapp-client-history-bookings", initData],
    queryFn: () => loadClientHistoryBookings(initData),
    enabled: Boolean(initData) && resolvedMode === "client" && activeTabKey === "history"
  });

  const profileQuery = useQuery({
    queryKey: ["miniapp-client-profile", initData],
    queryFn: () => loadClientProfile(initData),
    enabled: Boolean(initData) && resolvedMode === "client" && activeTabKey === "profile"
  });

  const adminBookingsQuery = useQuery({
    queryKey: ["miniapp-admin-bookings", initData],
    queryFn: () =>
      loadAdminBookings({
        initData
      }),
    enabled: Boolean(initData) && resolvedMode === "admin" && activeTabKey === "requests"
  });

  const adminBookingCardQuery = useQuery({
    queryKey: ["miniapp-admin-booking-card", initData, selectedAdminBookingId],
    queryFn: () => loadAdminBooking(initData, selectedAdminBookingId as number),
    enabled:
      Boolean(initData) &&
      resolvedMode === "admin" &&
      activeTabKey === "requests" &&
      selectedAdminBookingId !== null
  });

  const adminCalendarOverviewQuery = useQuery({
    queryKey: ["miniapp-admin-calendar-overview", initData, calendarRangeStart, calendarQueryDays],
    queryFn: () =>
      loadAdminCalendarOverview({
        initData,
        fromDate: calendarRangeStart,
        days: calendarQueryDays
      }),
    enabled: Boolean(initData) && resolvedMode === "admin" && activeTabKey === "calendar"
  });

  const adminAvailabilitySettingsQuery = useQuery({
    queryKey: ["miniapp-admin-availability-settings", initData],
    queryFn: () =>
      loadAdminAvailabilitySettings({
        initData,
        fromDate: todayIso,
        days: 60
      }),
    enabled: Boolean(initData) && resolvedMode === "admin" && activeTabKey === "settings"
  });

  useEffect(() => {
    if (!profileQuery.data) {
      return;
    }
    setProfileForm({
      name: profileQuery.data.profile.name ?? "",
      email: profileQuery.data.profile.email ?? "",
      phone: profileQuery.data.profile.phone ?? ""
    });
  }, [profileQuery.data]);

  useEffect(() => {
    if (!adminBookingCardQuery.data) {
      return;
    }
    setAdminMetaForm({
      admin_public_comment: adminBookingCardQuery.data.admin_public_comment ?? "",
      meeting_link: adminBookingCardQuery.data.meeting_link ?? ""
    });
  }, [adminBookingCardQuery.data]);

  useEffect(() => {
    if (!adminAvailabilitySettingsQuery.data) {
      return;
    }
    const minLead = adminAvailabilitySettingsQuery.data.min_lead_minutes;
    setMinLeadMinutesInput(String(minLead ?? 60));
  }, [adminAvailabilitySettingsQuery.data]);

  useEffect(() => {
    if (resolvedMode === "client" && activeTabKey === "bookings") {
      setClientQuickFilter("all");
      return;
    }
    if (resolvedMode === "admin" && activeTabKey === "requests") {
      setAdminQuickView("needs_action");
      return;
    }
    if (resolvedMode === "admin" && activeTabKey === "calendar") {
      setCalendarUseCurrentWeek(true);
      setCalendarFromDate(todayIso);
    }
  }, [resolvedMode, activeTabKey, todayIso]);

  useEffect(() => {
    setActionMessage("");
    setRescheduleState(null);
    setRescheduleError("");
    setSelectedAdminBookingId(null);
  }, [activeTabKey]);

  useEffect(() => {
    if (!selectedAdminBookingId) {
      return;
    }
    const exists = (adminBookingsQuery.data?.items ?? []).some(
      (item) => item.booking_id === selectedAdminBookingId
    );
    if (!exists) {
      setSelectedAdminBookingId(null);
    }
  }, [adminBookingsQuery.data, selectedAdminBookingId]);

  useEffect(() => {
    setSelectedAdminBookingId(null);
  }, [adminQuickView]);

  useEffect(() => {
    if (!actionMessage) {
      return;
    }
    const timeout = setTimeout(() => setActionMessage(""), 3500);
    return () => clearTimeout(timeout);
  }, [actionMessage]);

  const cancelBookingMutation = useMutation({
    mutationFn: (bookingId: number) => cancelClientBooking(bookingId, initData),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      setCancelDialog(null);
      setRescheduleState(null);
      setRescheduleError("");
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-active-bookings", initData] });
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-history-bookings", initData] });
    },
    onError: (error: Error) => {
      setCancelDialog((prev) =>
        prev
          ? {
              ...prev,
              error: error.message || "Не удалось отменить заявку."
            }
          : prev
      );
    }
  });

  const startRescheduleMutation = useMutation({
    mutationFn: ({ bookingId }: { bookingId: number; topic: string }) =>
      startClientReschedule(bookingId, initData),
    onSuccess: (payload) => {
      const firstWeek = payload.available_slots.week_options[0]?.key ?? "";
      const firstDay = payload.available_slots.day_options_by_week[firstWeek]?.[0]?.key ?? "";
      const firstSlot = payload.available_slots.time_options_by_day[firstDay]?.[0] ?? null;
      const topic = startRescheduleMutation.variables?.topic ?? "Без темы";
      setRescheduleState({
        bookingId: payload.booking_id,
        topic,
        currentSlotLabel: formatSlot(payload.current_slot_start_at, payload.current_slot_end_at),
        slotsData: payload.available_slots,
        selectedWeek: firstWeek,
        selectedDay: firstDay,
        selectedSlot: firstSlot
      });
      setActionMessage(payload.message);
      setRescheduleError("");
    },
    onError: (error: Error) => {
      setRescheduleError(error.message || "Не удалось открыть перенос заявки.");
    }
  });

  const submitRescheduleMutation = useMutation({
    mutationFn: () => {
      if (!rescheduleState?.selectedSlot) {
        throw new Error("Выберите новый слот для переноса.");
      }
      return submitClientReschedule(
        rescheduleState.bookingId,
        initData,
        rescheduleState.selectedSlot.slot_key
      );
    },
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      setRescheduleState(null);
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-active-bookings", initData] });
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-history-bookings", initData] });
    },
    onError: (error: Error) => {
      setRescheduleError(error.message || "Не удалось отправить запрос на перенос.");
    }
  });

  const updateProfileMutation = useMutation({
    mutationFn: () =>
      updateClientProfile({
        init_data: initData,
        name: profileForm.name,
        email: profileForm.email,
        phone: profileForm.phone
      }),
    onSuccess: () => {
      setActionMessage("Профиль обновлён.");
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-profile", initData] });
      void queryClient.invalidateQueries({ queryKey: ["miniapp-auth-session", initData] });
    }
  });

  const confirmAdminMutation = useMutation({
    mutationFn: ({ bookingId, payload }: { bookingId: number; payload: { admin_public_comment?: string; meeting_link?: string } }) =>
      confirmAdminBooking(initData, bookingId, payload),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      setSelectedAdminBookingId(null);
      void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-bookings"] });
      void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-booking-card"] });
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось подтвердить заявку.");
    }
  });

  const rejectAdminMutation = useMutation({
    mutationFn: ({ bookingId, payload }: { bookingId: number; payload: { admin_public_comment?: string; meeting_link?: string } }) =>
      rejectAdminBooking(initData, bookingId, payload),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      setSelectedAdminBookingId(null);
      void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-bookings"] });
      void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-booking-card"] });
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось отклонить заявку.");
    }
  });

  const invalidateAdminAvailability = () => {
    void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-calendar-overview"] });
    void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-availability-settings"] });
  };

  const updateMinLeadMutation = useMutation({
    mutationFn: () =>
      updateAdminMinLead({
        init_data: initData,
        minutes: Number(minLeadMinutesInput)
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось обновить минимальный интервал.");
    }
  });

  const saveWorkingWindowMutation = useMutation({
    mutationFn: async () => {
      const weekday = Number(workingWindowForm.weekday);
      const startTime = workingWindowForm.start_time;
      const endTime = workingWindowForm.end_time;
      const toMinutes = (value: string) => {
        const [hours, minutes] = value.split(":").map((item) => Number(item));
        return hours * 60 + minutes;
      };
      const startMinutes = toMinutes(startTime);
      const endMinutes = toMinutes(endTime);
      if (endMinutes <= startMinutes) {
        throw new Error("Время окончания должно быть позже времени начала.");
      }
      const hasSameInterval = selectedWeekdayWindows.some(
        (item) => item.start_time === startTime && item.end_time === endTime
      );
      if (hasSameInterval) {
        return { message: "Такой интервал уже установлен для выбранного дня." };
      }
      const overlapping = selectedWeekdayWindows.filter((item) => {
        const itemStart = toMinutes(item.start_time);
        const itemEnd = toMinutes(item.end_time);
        return startMinutes < itemEnd && endMinutes > itemStart;
      });

      if (overlapping.length > 0) {
        await Promise.all(
          overlapping.map((item) =>
            removeAdminWorkingWindow({
              init_data: initData,
              rule_id: item.rule_id
            })
          )
        );
        await addAdminWorkingWindow({
          init_data: initData,
          weekday,
          start_time: startTime,
          end_time: endTime
        });
        return { message: "Интервал обновлён для выбранного дня." };
      }
      return addAdminWorkingWindow({
        init_data: initData,
        weekday,
        start_time: startTime,
        end_time: endTime
      });
    },
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      setWorkingWindowFeedback(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось сохранить рабочее время.");
      setWorkingWindowFeedback(error.message || "Не удалось сохранить время для встреч.");
    }
  });

  const clearWorkingWindowMutation = useMutation({
    mutationFn: (weekday?: number) =>
      clearAdminWorkingWindows({
        init_data: initData,
        weekday
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      setWorkingWindowFeedback(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось очистить рабочие окна.");
      setWorkingWindowFeedback(error.message || "Не удалось удалить интервалы дня.");
    }
  });

  const closeDayMutation = useMutation({
    mutationFn: () =>
      closeAdminDay({
        init_data: initData,
        date: closedDayForm.date,
        reason: closedDayForm.reason.trim() || undefined
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
      void queryClient.invalidateQueries({ queryKey: ["miniapp-admin-bookings"] });
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось закрыть день.");
    }
  });

  const reopenDayMutation = useMutation({
    mutationFn: () =>
      reopenAdminDay({
        init_data: initData,
        date: closedDayForm.date
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось открыть день.");
    }
  });

  const reopenSpecificDayMutation = useMutation({
    mutationFn: (dateValue: string) =>
      reopenAdminDay({
        init_data: initData,
        date: dateValue
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось открыть день.");
    }
  });

  const addTimeBlockMutation = useMutation({
    mutationFn: () =>
      addAdminTimeBlock({
        init_data: initData,
        date: timeBlockForm.date,
        start_time: timeBlockForm.start_time,
        end_time: timeBlockForm.end_time,
        comment: timeBlockForm.comment.trim() || undefined
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось добавить внутренний блок.");
    }
  });

  const removeTimeBlockMutation = useMutation({
    mutationFn: (blockId: number) =>
      removeAdminTimeBlock({
        init_data: initData,
        block_id: blockId
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось удалить внутренний блок.");
    }
  });

  const addOneTimeWindowMutation = useMutation({
    mutationFn: () =>
      addAdminOneTimeWindow({
        init_data: initData,
        date: oneTimeWindowForm.date,
        start_time: oneTimeWindowForm.start_time,
        end_time: oneTimeWindowForm.end_time,
        comment: oneTimeWindowForm.comment.trim() || undefined
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось добавить окно на дату.");
    }
  });

  const removeOneTimeWindowsByDateMutation = useMutation({
    mutationFn: (dateValue: string) =>
      removeAdminOneTimeWindowsByDate({
        init_data: initData,
        date: dateValue
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось удалить окна на дату.");
    }
  });

  const removeOneTimeWindowMutation = useMutation({
    mutationFn: ({ date, start_time, end_time }: { date: string; start_time: string; end_time: string }) =>
      removeAdminOneTimeWindow({
        init_data: initData,
        date,
        start_time,
        end_time
      }),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      invalidateAdminAvailability();
    },
    onError: (error: Error) => {
      setActionMessage(error.message || "Не удалось удалить индивидуальное окно.");
    }
  });

  useEffect(() => {
    setActiveTabKey(navItems[0].key);
  }, [resolvedMode]);

  if (!initData) {
    return (
      <main className={styles.page}>
        <section className={styles.card}>
          <div className={styles.brand}>ER Meet</div>
          <h1>Нужен запуск из Telegram</h1>
          <p>
            Mini App ожидает Telegram `initData`. Откройте приложение через кнопку в боте, чтобы
            пройти безопасную авторизацию.
          </p>
        </section>
      </main>
    );
  }

  if (sessionQuery.isError) {
    return (
      <main className={styles.page}>
        <section className={styles.card}>
          <div className={styles.brand}>ER Meet</div>
          <h1>Не удалось открыть приложение</h1>
          <p>{sessionQuery.error.message}</p>
          <div className={styles.actionsRow}>
            <button type="button" onClick={() => sessionQuery.refetch()} className={styles.button}>
              Попробовать снова
            </button>
            <button
              type="button"
              onClick={() => getTelegramWebApp()?.close?.()}
              className={styles.buttonGhost}
            >
              Вернуться в бот
            </button>
          </div>
        </section>
      </main>
    );
  }

  if (sessionQuery.isPending || !sessionQuery.data || !resolvedMode) {
    return (
      <main className={styles.page}>
        <section className={styles.card}>
          <div className={styles.brand}>ER Meet</div>
          <h1>Загрузка</h1>
          <p>Проверяем доступ и подготавливаем рабочее пространство Mini App.</p>
        </section>
      </main>
    );
  }

  const authPayload = sessionQuery.data;
  const currentTab =
    navItems.find((item) => item.key === activeTabKey) ??
    navItems.find((item) => item.key === "home") ??
    navItems[0];
  const isHomeTab = currentTab.key === "home";
  const canSwitchMode = authPayload.access.is_admin;
  const isClientCabinetTab = resolvedMode === "client" && currentTab.key !== "home";
  const isAdminRequestsTab = resolvedMode === "admin" && currentTab.key === "requests";
  const isAdminCalendarTab = resolvedMode === "admin" && currentTab.key === "calendar";
  const isAdminSettingsTab = resolvedMode === "admin" && currentTab.key === "settings";
  const upcomingClosedDays =
    adminAvailabilitySettingsQuery.data?.closed_days.filter((item) => item.date >= todayIso) ?? [];
  const upcomingOneTimeWindows =
    adminAvailabilitySettingsQuery.data?.one_time_windows.filter((item) => item.date >= todayIso) ?? [];
  const upcomingTimeBlocks =
    adminAvailabilitySettingsQuery.data?.time_blocks.filter((item) => item.date >= todayIso) ?? [];
  const selectedWeekdayWindows =
    adminAvailabilitySettingsQuery.data?.working_windows.filter(
      (item) => item.weekday === Number(workingWindowForm.weekday)
    ) ?? [];
  const workingWindowsByWeekday = (() => {
    const map = new Map<number, Array<{ rule_id: number; start_time: string; end_time: string }>>();
    for (const item of adminAvailabilitySettingsQuery.data?.working_windows ?? []) {
      const list = map.get(item.weekday) ?? [];
      list.push({ rule_id: item.rule_id, start_time: item.start_time, end_time: item.end_time });
      map.set(item.weekday, list);
    }
    for (const [weekday, list] of map.entries()) {
      list.sort((a, b) => a.start_time.localeCompare(b.start_time));
      map.set(weekday, list);
    }
    return map;
  })();
  const currentWeekMondayIso = toIsoDate(startOfWeek(new Date()));
  const isViewingCurrentWeek = (() => {
    if (calendarUseCurrentWeek) {
      return true;
    }
    return toIsoDate(startOfWeek(parseIsoDate(calendarFromDate))) === currentWeekMondayIso;
  })();
  const adminVisibleItems = (adminBookingsQuery.data?.items ?? []).filter((item) => {
    const isPastConfirmed =
      item.status === "confirmed" &&
      Boolean(item.slot_end_at) &&
      new Date(item.slot_end_at as string).getTime() < Date.now();
    if (adminQuickView === "needs_action") {
      return item.status === "pending_decision" || item.status === "reschedule_requested";
    }
    if (adminQuickView === "confirmed") {
      return item.status === "confirmed" && !isPastConfirmed;
    }
    if (adminQuickView === "canceled") {
      return ADMIN_ARCHIVE_STATUSES.has(item.status);
    }
    if (adminQuickView === "archive") {
      return isPastConfirmed;
    }
    return true;
  });
  const sortedClientItems = [...(activeBookingsQuery.data?.items ?? [])].sort((left, right) => {
    const leftPriority = CLIENT_BOOKING_PRIORITY[left.status] ?? 99;
    const rightPriority = CLIENT_BOOKING_PRIORITY[right.status] ?? 99;
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }
    const leftTs = left.slot_start_at ? new Date(left.slot_start_at).getTime() : Number.POSITIVE_INFINITY;
    const rightTs = right.slot_start_at ? new Date(right.slot_start_at).getTime() : Number.POSITIVE_INFINITY;
    if (leftTs !== rightTs) {
      return leftTs - rightTs;
    }
    return left.booking_id - right.booking_id;
  });
  const clientFilteredItems = sortedClientItems.filter((item) => {
    if (clientQuickFilter === "all") {
      return true;
    }
    return CLIENT_FILTER_STATUS_MAP[clientQuickFilter].has(item.status);
  });

  function toAdminDecisionPayload() {
    const payload: { admin_public_comment?: string; meeting_link?: string } = {};
    const comment = adminMetaForm.admin_public_comment.trim();
    const link = adminMetaForm.meeting_link.trim();
    if (comment) {
      payload.admin_public_comment = comment;
    }
    if (link) {
      payload.meeting_link = link;
    }
    return payload;
  }

  function selectClientFilter(filter: ClientQuickFilter) {
    setClientQuickFilter(filter);
  }

  function shiftCalendarStart(direction: number) {
    if (calendarUseCurrentWeek) {
      const currentWeekMonday = startOfWeek(new Date());
      const targetWeekMonday = addDays(currentWeekMonday, direction > 0 ? 7 : -7);
      setCalendarFromDate(toIsoDate(targetWeekMonday));
      setCalendarUseCurrentWeek(false);
      return;
    }
    const base = addDays(parseIsoDate(calendarFromDate), direction * 7);
    setCalendarFromDate(toIsoDate(startOfWeek(base)));
  }

  function renderBookingCard(item: ClientBookingItem, showActions: boolean) {
    const statusClass =
      item.status === "confirmed"
        ? styles.bookingCardConfirmed
        : item.status === "pending_decision"
          ? styles.bookingCardPending
          : item.status === "reschedule_requested"
            ? styles.bookingCardReschedule
            : styles.bookingCardNeutral;
    return (
      <article key={item.booking_id} className={`${styles.bookingCard} ${statusClass}`}>
        <div className={styles.cardHead}>
          <h3>{item.topic || "Заявка без темы"}</h3>
          <span className={`${styles.statusBadge} ${statusBadgeClass(item.status)}`}>
            {statusLabelForCard(item.status, item.slot_end_at)}
          </span>
        </div>
        <p className={styles.softText}>Время: {formatSlot(item.slot_start_at, item.slot_end_at)}</p>
        <p className={styles.softText}>Формат: {item.meeting_format || "не указан"}</p>
        <p className={styles.softText}>Длительность: {item.duration_minutes || "—"} мин</p>
        {item.comment ? <p className={styles.softText}>Комментарий: {item.comment}</p> : null}
        {item.admin_public_comment ? (
          <p className={styles.softText}>Комментарий администратора: {item.admin_public_comment}</p>
        ) : null}
        {item.meeting_link ? (
          <p className={styles.softText}>
            Ссылка на встречу:{" "}
            <a href={item.meeting_link} target="_blank" rel="noreferrer">
              открыть
            </a>
          </p>
        ) : null}
        {showActions ? (
          <div className={styles.cardActions}>
            <button
              type="button"
              className={styles.buttonGhost}
              onClick={() =>
                setCancelDialog({
                  bookingId: item.booking_id,
                  topic: item.topic || "Заявка без темы",
                  comment: "",
                  error: ""
                })
              }
              disabled={cancelBookingMutation.isPending}
            >
              Отменить
            </button>
            <button
              type="button"
              className={styles.button}
              onClick={() =>
                startRescheduleMutation.mutate({
                  bookingId: item.booking_id,
                  topic: item.topic || "Без темы"
                })
              }
              disabled={startRescheduleMutation.isPending}
            >
              Перенести
            </button>
          </div>
        ) : null}
      </article>
    );
  }

  function renderAdminBookingCard(item: AdminBookingItem) {
    const statusClass =
      item.status === "confirmed"
        ? styles.bookingCardConfirmed
        : item.status === "pending_decision"
          ? styles.bookingCardPending
          : item.status === "reschedule_requested"
            ? styles.bookingCardReschedule
            : styles.bookingCardNeutral;
    const contactsLabel = [item.user.email, item.user.phone].filter(Boolean).join(" • ") || "не указаны";
    return (
      <article
        key={item.booking_id}
        className={`${styles.bookingCard} ${styles.bookingCardClickable} ${statusClass}`}
        onClick={() => setSelectedAdminBookingId(item.booking_id)}
      >
        <div className={styles.cardHead}>
          <h3>{item.topic || "Заявка без темы"}</h3>
          <span className={`${styles.statusBadge} ${statusBadgeClass(item.status)}`}>
            {statusLabelForCard(item.status, item.slot_end_at)}
          </span>
        </div>
        <p className={styles.softText}>Клиент: {formatAdminClientName(item.user)}</p>
        <p className={styles.softText}>Telegram: {formatTelegramUsername(item.user.telegram_username)}</p>
        <p className={styles.softText}>Контакты: {contactsLabel}</p>
        <p className={styles.softText}>Время: {formatSlot(item.slot_start_at, item.slot_end_at)}</p>
        <p className={styles.softText}>Формат: {item.meeting_format || "не указан"}</p>
        <p className={styles.softText}>Длительность: {item.duration_minutes || "—"} мин</p>
        {item.comment ? <p className={styles.softText}>Комментарий клиента: {item.comment}</p> : null}
      </article>
    );
  }

  function renderAdminCalendarDay(day: AdminCalendarDay) {
    const hasLoad = day.pending_count + day.confirmed_count + day.reschedule_count > 0;
    return (
      <article key={day.date} className={`${styles.bookingCard} ${styles.bookingCardNeutral}`}>
        <div className={styles.cardHead}>
          <h3>{formatDayLabel(day.date)}</h3>
          <div className={styles.badgeRow}>
            {day.is_closed ? <span className={`${styles.statusBadge} ${styles.statusBadgeDanger}`}>Закрыт</span> : null}
            {day.confirmed_count ? (
              <span className={`${styles.statusBadge} ${styles.statusBadgeCalendarConfirmed}`}>
                Подтверждённых встреч: {day.confirmed_count}
              </span>
            ) : null}
          </div>
        </div>
        {day.closed_reason ? <p className={styles.softText}>Причина: {day.closed_reason}</p> : null}
        <p className={styles.softText}>
          Время для встреч:{" "}
          {day.working_windows.length
            ? day.working_windows.map((window) => `${window.start_time} - ${window.end_time}`).join(", ")
            : "нет"}
        </p>
        <p className={styles.softText}>
          Исключения времени:{" "}
          {day.time_blocks.length
            ? day.time_blocks.map((block) => `${block.start_time} - ${block.end_time}`).join(", ")
            : "нет"}
        </p>
        {hasLoad && day.bookings_preview.length ? (
          <div className={styles.previewList}>
            {day.bookings_preview.map((preview) => (
              <div key={preview.booking_id} className={styles.meetingPreviewCard}>
                <div className={styles.cardHead}>
                  <p className={styles.softText}>#{preview.booking_id} · {preview.topic || "Без темы"}</p>
                  <span className={`${styles.statusBadge} ${statusBadgeClass(preview.status)}`}>
                    {statusLabel(preview.status)}
                  </span>
                </div>
                <p className={styles.softText}>
                  Клиент: {preview.client_name || formatTelegramUsername(preview.client_username)}
                </p>
                <p className={styles.softText}>
                  Время: {formatTimeRange(preview.slot_start_at, preview.slot_end_at)}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.softText}>Встреч в этот день пока нет.</p>
        )}
      </article>
    );
  }

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <header className={styles.header}>
          {isHomeTab ? (
            <div className={styles.heroStack}>
              <div className={styles.brand}>ER Meet</div>
              <h1>Запись на встречу с Еленой</h1>
              <div className={styles.photoPlaceholder}>
                {!photoLoadFailed && hostPhotoUrl ? (
                  <img
                    src={hostPhotoUrl}
                    alt="Фото Елены"
                    className={styles.photoImage}
                    onError={() => setPhotoLoadFailed(true)}
                  />
                ) : (
                  <span aria-hidden="true">Фото</span>
                )}
              </div>
            </div>
          ) : resolvedMode === "admin" ? (
            <>
              <div className={styles.brand}>ER Meet</div>
              <h1>{currentTab.key === "requests" ? "Список заявок" : currentTab.title}</h1>
            </>
          ) : (
            <>
              <div className={styles.brand}>ER Meet</div>
              <h1>Запись на встречу с Еленой</h1>
            </>
          )}
        </header>

        {currentTab.key === "home" ? (
          <section className={styles.content}>
            <div className={styles.contentTop}>
              <div className={styles.featureCard}>
                <h3>В каких вопросах могу быть полезна</h3>
                <ul>
                  <li>Финансовая аналитика и управленческие решения</li>
                  <li>Автоматизация учёта и бизнес-процессов</li>
                  <li>Vibe-coding, обсуждение идей и обмен опытом</li>
                </ul>
              </div>
            </div>

            <div className={styles.contentBottom}>
              <h2 className={styles.centeredTitle}>
                Здравствуйте, {profileForm.name.trim() || getFirstName(authPayload)}.
              </h2>
              <p className={styles.softText}>Выберите удобное время для встречи.</p>
              {resolvedMode === "client" ? (
                <button type="button" className={styles.primaryCta} onClick={() => setNewBookingOpen(true)}>
                  Записаться на встречу
                </button>
              ) : null}
            </div>
          </section>
        ) : isClientCabinetTab ? (
          <section className={styles.content}>
            <h2>{currentTab.title}</h2>
            <p className={styles.softText}>{currentTab.subtitle}</p>
            {actionMessage ? <p className={styles.notice}>{actionMessage}</p> : null}

            {currentTab.key === "bookings" ? (
              <div className={styles.listBlock}>
                <div className={styles.quickFilterRow}>
                  <button
                    type="button"
                    className={clientQuickFilter === "all" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => selectClientFilter("all")}
                  >
                    Все
                  </button>
                  <button
                    type="button"
                    className={clientQuickFilter === "pending" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => selectClientFilter("pending")}
                  >
                    Ожидают решения
                  </button>
                  <button
                    type="button"
                    className={clientQuickFilter === "confirmed" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => selectClientFilter("confirmed")}
                  >
                    Подтверждённые
                  </button>
                  <button
                    type="button"
                    className={clientQuickFilter === "draft" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => selectClientFilter("draft")}
                  >
                    Черновики
                  </button>
                  <button
                    type="button"
                    className={clientQuickFilter === "canceled" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => selectClientFilter("canceled")}
                  >
                    Отменённые
                  </button>
                </div>
                {activeBookingsQuery.isPending ? <p className={styles.softText}>Загружаем активные заявки...</p> : null}
                {activeBookingsQuery.isError ? (
                  <p className={styles.errorText}>Не удалось загрузить активные заявки.</p>
                ) : null}
                {clientFilteredItems.length ? (
                  clientFilteredItems.map((item) => renderBookingCard(item, true))
                ) : (
                  <p className={styles.softText}>Заявок по выбранным фильтрам нет.</p>
                )}

              </div>
            ) : null}

            {currentTab.key === "history" ? (
              <div className={styles.listBlock}>
                {historyBookingsQuery.isPending ? <p className={styles.softText}>Загружаем историю...</p> : null}
                {historyBookingsQuery.isError ? <p className={styles.errorText}>Не удалось загрузить историю.</p> : null}
                {historyBookingsQuery.data?.items.length ? (
                  historyBookingsQuery.data.items.map((item) => renderBookingCard(item, false))
                ) : (
                  <p className={styles.softText}>История встреч пока пуста.</p>
                )}
              </div>
            ) : null}

            {currentTab.key === "profile" ? (
              <div className={styles.profileCard}>
                <label className={styles.field}>
                  <span>Имя</span>
                  <input
                    value={profileForm.name}
                    onChange={(event) => setProfileForm((prev) => ({ ...prev, name: event.target.value }))}
                  />
                </label>
                <label className={styles.field}>
                  <span>Email</span>
                  <input
                    value={profileForm.email}
                    onChange={(event) => setProfileForm((prev) => ({ ...prev, email: event.target.value }))}
                  />
                </label>
                <label className={styles.field}>
                  <span>Телефон</span>
                  <input
                    value={profileForm.phone}
                    onChange={(event) => setProfileForm((prev) => ({ ...prev, phone: event.target.value }))}
                  />
                </label>
                <p className={styles.softText}>
                  Напоминания: скоро появятся в одном из следующих этапов.
                </p>
                <button
                  type="button"
                  className={`${styles.primaryCta} ${styles.centeredButton}`}
                  onClick={() => updateProfileMutation.mutate()}
                  disabled={updateProfileMutation.isPending || profileQuery.isPending}
                >
                  Сохранить профиль
                </button>
              </div>
            ) : null}
          </section>
        ) : isAdminRequestsTab ? (
          <section className={styles.content}>
            {actionMessage ? <p className={styles.notice}>{actionMessage}</p> : null}

            <div className={styles.quickFilterRow}>
              <button
                type="button"
                className={adminQuickView === "needs_action" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => setAdminQuickView("needs_action")}
              >
                Требуют решения
              </button>
              <button
                type="button"
                className={adminQuickView === "confirmed" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => setAdminQuickView("confirmed")}
              >
                Подтверждённые
              </button>
              <button
                type="button"
                className={adminQuickView === "canceled" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => setAdminQuickView("canceled")}
              >
                Отменённые
              </button>
              <button
                type="button"
                className={adminQuickView === "archive" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => setAdminQuickView("archive")}
              >
                Архив
              </button>
              <button
                type="button"
                className={adminQuickView === "all" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => setAdminQuickView("all")}
              >
                Все
              </button>
            </div>

            <div className={styles.listBlock}>
              {adminBookingsQuery.isPending ? <p className={styles.softText}>Загружаем заявки...</p> : null}
              {adminBookingsQuery.isError ? (
                <p className={styles.errorText}>
                  Не удалось загрузить заявки: {adminBookingsQuery.error?.message || "ошибка API."}
                </p>
              ) : null}
              {!adminBookingsQuery.isPending && !adminBookingsQuery.isError && adminVisibleItems.length ? (
                adminVisibleItems.map((item) => renderAdminBookingCard(item))
              ) : null}
              {!adminBookingsQuery.isPending && !adminBookingsQuery.isError && !adminVisibleItems.length ? (
                <p className={styles.softText}>Заявок в этом разделе пока нет.</p>
              ) : null}
            </div>
          </section>
        ) : isAdminCalendarTab ? (
          <section className={styles.content}>
            {actionMessage ? <p className={styles.notice}>{actionMessage}</p> : null}
            <div className={styles.weekNav}>
              <button type="button" className={styles.modeButton} onClick={() => shiftCalendarStart(-1)}>
                ←
              </button>
              <p className={styles.weekLabel}>
                Период: {calendarRangeLabel}
              </p>
              <button type="button" className={styles.modeButton} onClick={() => shiftCalendarStart(1)}>
                →
              </button>
            </div>
            {!isViewingCurrentWeek ? (
              <div className={styles.cardActions}>
                <button
                  type="button"
                  className={styles.buttonGhost}
                  onClick={() => {
                    setCalendarUseCurrentWeek(true);
                    setCalendarFromDate(todayIso);
                  }}
                >
                  Вернуться в текущую неделю
                </button>
              </div>
            ) : null}
            <div className={styles.listBlock}>
              {adminCalendarOverviewQuery.isPending ? <p className={styles.softText}>Загружаем обзор...</p> : null}
              {adminCalendarOverviewQuery.isError ? (
                <p className={styles.errorText}>Не удалось загрузить календарный обзор.</p>
              ) : null}
              {adminCalendarOverviewQuery.data?.items.length
                ? adminCalendarOverviewQuery.data.items.map((day) => renderAdminCalendarDay(day))
                : null}
            </div>
          </section>
        ) : isAdminSettingsTab ? (
          <section className={styles.content}>
            {actionMessage ? <p className={styles.notice}>{actionMessage}</p> : null}
            {adminAvailabilitySettingsQuery.isPending ? <p className={styles.softText}>Загружаем настройки...</p> : null}
            {adminAvailabilitySettingsQuery.isError ? (
              <p className={styles.errorText}>Не удалось загрузить настройки доступности.</p>
            ) : null}
            <div className={styles.settingsStack}>
              <section className={styles.settingsSection}>
                <button
                  type="button"
                  className={styles.settingsSectionHead}
                  onClick={() => setOpenAdminSection((prev) => (prev === "lead" ? null : "lead"))}
                >
                  <div>
                    <h3>Настройки доступности</h3>
                    <p className={styles.softText}>
                      Минимальный интервал до встречи: {adminAvailabilitySettingsQuery.data?.min_lead_minutes ?? 0} минут.
                    </p>
                  </div>
                  <span className={styles.sectionToggle}>{openAdminSection === "lead" ? "Свернуть" : "Изменить"}</span>
                </button>
                {openAdminSection === "lead" ? (
                  <div className={styles.settingsSectionBody}>
                    <label className={styles.field}>
                      <span>Минимальный интервал до встречи (минут)</span>
                      <input
                        type="number"
                        min={0}
                        max={10080}
                        value={minLeadMinutesInput}
                        onChange={(event) => setMinLeadMinutesInput(event.target.value)}
                      />
                    </label>
                    <div className={styles.cardActions}>
                      <button
                        type="button"
                        className={styles.button}
                        onClick={() => updateMinLeadMutation.mutate()}
                        disabled={updateMinLeadMutation.isPending}
                      >
                        Сохранить интервал
                      </button>
                    </div>
                  </div>
                ) : null}
              </section>

              <section className={styles.settingsSection}>
                <button
                  type="button"
                  className={styles.settingsSectionHead}
                  onClick={() => setOpenAdminSection((prev) => (prev === "windows" ? null : "windows"))}
                >
                  <div>
                    <h3>Время для встреч</h3>
                    <p className={styles.softText}>
                      Повторяющееся расписание по дням недели. Дней с расписанием: {workingWindowsByWeekday.size}.
                    </p>
                    <p className={styles.softText}>
                      Можно добавить несколько непересекающихся интервалов в один день (например, 10:00-13:00 и 15:00-17:00).
                    </p>
                  </div>
                  <span className={styles.sectionToggle}>
                    {openAdminSection === "windows" ? "Свернуть" : "Изменить"}
                  </span>
                </button>
                {openAdminSection === "windows" ? (
                  <div className={styles.settingsSectionBody}>
                    {workingWindowsByWeekday.size ? (
                      <div className={styles.listBlock}>
                        <p className={styles.softText}>Текущее расписание:</p>
                        {[0, 1, 2, 3, 4, 5, 6].map((weekday) => {
                          const items = workingWindowsByWeekday.get(weekday) ?? [];
                          if (!items.length) {
                            return null;
                          }
                          return (
                            <p key={weekday} className={styles.softText}>
                              {weekdayLabel(weekday)}: {items.map((item) => `${item.start_time}-${item.end_time}`).join(", ")}
                            </p>
                          );
                        })}
                      </div>
                    ) : (
                      <p className={styles.softText}>Повторяющееся расписание пока не задано.</p>
                    )}

                    <label className={styles.field}>
                      <span>День недели</span>
                      <select
                        value={workingWindowForm.weekday}
                        onChange={(event) => {
                          setWorkingWindowForm((prev) => ({ ...prev, weekday: event.target.value }));
                          setWorkingWindowFeedback("");
                        }}
                      >
                        {[0, 1, 2, 3, 4, 5, 6].map((weekday) => (
                          <option key={weekday} value={weekday}>
                            {weekdayLabel(weekday)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className={styles.dualFields}>
                      <label className={styles.field}>
                        <span>С</span>
                        <input
                          type="time"
                          value={workingWindowForm.start_time}
                          onChange={(event) =>
                            setWorkingWindowForm((prev) => ({ ...prev, start_time: event.target.value }))
                          }
                        />
                      </label>
                      <label className={styles.field}>
                        <span>По</span>
                        <input
                          type="time"
                          value={workingWindowForm.end_time}
                          onChange={(event) =>
                            setWorkingWindowForm((prev) => ({ ...prev, end_time: event.target.value }))
                          }
                        />
                      </label>
                    </div>
                    <div className={styles.cardActions}>
                      <button
                        type="button"
                        className={styles.button}
                        onClick={() => saveWorkingWindowMutation.mutate()}
                        disabled={saveWorkingWindowMutation.isPending}
                      >
                        Сохранить время
                      </button>
                      <button
                        type="button"
                        className={styles.buttonGhost}
                        onClick={() => clearWorkingWindowMutation.mutate(Number(workingWindowForm.weekday))}
                        disabled={clearWorkingWindowMutation.isPending}
                      >
                        Очистить день
                      </button>
                    </div>
                    {workingWindowFeedback ? (
                      <p className={styles.notice}>{workingWindowFeedback}</p>
                    ) : null}
                    {selectedWeekdayWindows.length ? (
                      <div className={styles.listBlock}>
                        <p className={styles.softText}>
                          Текущее время для {weekdayLabel(Number(workingWindowForm.weekday)).toLowerCase()}:
                        </p>
                        <p className={styles.softText}>Интервалов: {selectedWeekdayWindows.length}</p>
                        {selectedWeekdayWindows.map((window) => (
                          <div key={window.rule_id}>
                            <p className={styles.softText}>
                              {window.start_time} - {window.end_time}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className={styles.softText}>Для выбранного дня недели время пока не задано.</p>
                    )}
                  </div>
                ) : null}
              </section>

              <section className={styles.settingsSection}>
                <button
                  type="button"
                  className={styles.settingsSectionHead}
                  onClick={() => setOpenAdminSection((prev) => (prev === "one_time" ? null : "one_time"))}
                >
                  <div>
                    <h3>Индивидуальное окно на дату</h3>
                    <p className={styles.softText}>
                      Используйте для добавления доступности на конкретный день. Ближайших окон: {upcomingOneTimeWindows.length}.
                    </p>
                  </div>
                  <span className={styles.sectionToggle}>
                    {openAdminSection === "one_time" ? "Свернуть" : "Изменить"}
                  </span>
                </button>
                {openAdminSection === "one_time" ? (
                  <div className={styles.settingsSectionBody}>
                    <label className={styles.field}>
                      <span>Дата</span>
                      <input
                        type="date"
                        value={oneTimeWindowForm.date}
                        onChange={(event) => setOneTimeWindowForm((prev) => ({ ...prev, date: event.target.value }))}
                      />
                    </label>
                    <div className={styles.dualFields}>
                      <label className={styles.field}>
                        <span>С</span>
                        <input
                          type="time"
                          value={oneTimeWindowForm.start_time}
                          onChange={(event) =>
                            setOneTimeWindowForm((prev) => ({ ...prev, start_time: event.target.value }))
                          }
                        />
                      </label>
                      <label className={styles.field}>
                        <span>По</span>
                        <input
                          type="time"
                          value={oneTimeWindowForm.end_time}
                          onChange={(event) =>
                            setOneTimeWindowForm((prev) => ({ ...prev, end_time: event.target.value }))
                          }
                        />
                      </label>
                    </div>
                    <label className={styles.field}>
                      <span>Комментарий</span>
                      <input
                        value={oneTimeWindowForm.comment}
                        onChange={(event) => setOneTimeWindowForm((prev) => ({ ...prev, comment: event.target.value }))}
                      />
                    </label>
                    <div className={styles.cardActions}>
                      <button
                        type="button"
                        className={styles.button}
                        onClick={() => addOneTimeWindowMutation.mutate()}
                        disabled={addOneTimeWindowMutation.isPending}
                      >
                        Добавить окно на дату
                      </button>
                      <button
                        type="button"
                        className={styles.buttonGhost}
                        onClick={() => removeOneTimeWindowsByDateMutation.mutate(oneTimeWindowForm.date)}
                        disabled={removeOneTimeWindowsByDateMutation.isPending}
                      >
                        Удалить окна этой даты
                      </button>
                    </div>
                    {upcomingOneTimeWindows.length ? (
                      <div className={styles.listBlock}>
                        <p className={styles.softText}>Ближайшие индивидуальные окна:</p>
                        {upcomingOneTimeWindows.slice(0, 8).map((item, index) => (
                          <div key={`${item.date}-${item.start_time}-${index}`} className={styles.inlineActionRow}>
                            <p className={styles.softText}>
                              {formatDayLabel(item.date)} · {item.start_time} - {item.end_time}
                              {item.comment ? ` · ${item.comment}` : ""}
                            </p>
                            <button
                              type="button"
                              className={styles.buttonGhost}
                              onClick={() =>
                                removeOneTimeWindowMutation.mutate({
                                  date: item.date,
                                  start_time: item.start_time,
                                  end_time: item.end_time
                                })
                              }
                              disabled={removeOneTimeWindowMutation.isPending}
                            >
                              Удалить
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className={styles.softText}>Индивидуальные окна пока не добавлены.</p>
                    )}
                  </div>
                ) : null}
              </section>

              <section className={styles.settingsSection}>
                <button
                  type="button"
                  className={styles.settingsSectionHead}
                  onClick={() => setOpenAdminSection((prev) => (prev === "closed_days" ? null : "closed_days"))}
                >
                  <div>
                    <h3>Закрытие / открытие дня</h3>
                    <p className={styles.softText}>Ближайших закрытых дат: {upcomingClosedDays.length}.</p>
                  </div>
                  <span className={styles.sectionToggle}>
                    {openAdminSection === "closed_days" ? "Свернуть" : "Изменить"}
                  </span>
                </button>
                {openAdminSection === "closed_days" ? (
                  <div className={styles.settingsSectionBody}>
                    <label className={styles.field}>
                      <span>Дата</span>
                      <input
                        type="date"
                        value={closedDayForm.date}
                        onChange={(event) => setClosedDayForm((prev) => ({ ...prev, date: event.target.value }))}
                      />
                    </label>
                    <label className={styles.field}>
                      <span>Причина (необязательно)</span>
                      <input
                        value={closedDayForm.reason}
                        onChange={(event) => setClosedDayForm((prev) => ({ ...prev, reason: event.target.value }))}
                      />
                    </label>
                    <div className={styles.cardActions}>
                      <button
                        type="button"
                        className={styles.button}
                        onClick={() => closeDayMutation.mutate()}
                        disabled={closeDayMutation.isPending}
                      >
                        Закрыть день
                      </button>
                      <button
                        type="button"
                        className={styles.buttonGhost}
                        onClick={() => reopenDayMutation.mutate()}
                        disabled={reopenDayMutation.isPending}
                      >
                        Открыть день
                      </button>
                    </div>
                    {upcomingClosedDays.length ? (
                      <div className={styles.listBlock}>
                        <p className={styles.softText}>Ближайшие закрытые даты:</p>
                        {upcomingClosedDays.slice(0, 10).map((item) => (
                          <div key={item.date} className={styles.inlineActionRow}>
                            <p className={styles.softText}>
                              {formatDayLabel(item.date)}{item.reason ? ` · ${item.reason}` : ""}
                            </p>
                            <button
                              type="button"
                              className={styles.buttonGhost}
                              onClick={() => reopenSpecificDayMutation.mutate(item.date)}
                              disabled={reopenSpecificDayMutation.isPending}
                            >
                              Открыть
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className={styles.softText}>Сейчас закрытых дат нет.</p>
                    )}
                  </div>
                ) : null}
              </section>

              <section className={styles.settingsSection}>
                <button
                  type="button"
                  className={styles.settingsSectionHead}
                  onClick={() => setOpenAdminSection((prev) => (prev === "time_blocks" ? null : "time_blocks"))}
                >
                  <div>
                    <h3>Исключения внутри рабочего дня</h3>
                    <p className={styles.softText}>Ближайших исключений: {upcomingTimeBlocks.length}.</p>
                  </div>
                  <span className={styles.sectionToggle}>
                    {openAdminSection === "time_blocks" ? "Свернуть" : "Изменить"}
                  </span>
                </button>
                {openAdminSection === "time_blocks" ? (
                  <div className={styles.settingsSectionBody}>
                    <p className={styles.softText}>
                      Эти настройки исключают выбранные интервалы из доступного времени (например, обед, личные дела или созвон).
                    </p>
                    <label className={styles.field}>
                      <span>Дата</span>
                      <input
                        type="date"
                        value={timeBlockForm.date}
                        onChange={(event) => setTimeBlockForm((prev) => ({ ...prev, date: event.target.value }))}
                      />
                    </label>
                    <div className={styles.dualFields}>
                      <label className={styles.field}>
                        <span>С</span>
                        <input
                          type="time"
                          value={timeBlockForm.start_time}
                          onChange={(event) => setTimeBlockForm((prev) => ({ ...prev, start_time: event.target.value }))}
                        />
                      </label>
                      <label className={styles.field}>
                        <span>По</span>
                        <input
                          type="time"
                          value={timeBlockForm.end_time}
                          onChange={(event) => setTimeBlockForm((prev) => ({ ...prev, end_time: event.target.value }))}
                        />
                      </label>
                    </div>
                    <label className={styles.field}>
                      <span>Комментарий</span>
                      <input
                        value={timeBlockForm.comment}
                        onChange={(event) => setTimeBlockForm((prev) => ({ ...prev, comment: event.target.value }))}
                      />
                    </label>
                    <div className={styles.cardActions}>
                      <button
                        type="button"
                        className={styles.button}
                        onClick={() => addTimeBlockMutation.mutate()}
                        disabled={addTimeBlockMutation.isPending}
                      >
                        Добавить блок
                      </button>
                    </div>
                    {upcomingTimeBlocks.length ? (
                      <div className={styles.listBlock}>
                        <p className={styles.softText}>Ближайшие исключения времени:</p>
                        {upcomingTimeBlocks.slice(0, 8).map((block) => (
                          <div key={block.block_id} className={styles.inlineActionRow}>
                            <p className={styles.softText}>
                              {formatDayLabel(block.date)} · {block.start_time} - {block.end_time}{" "}
                              {block.comment ? `· ${block.comment}` : ""}
                            </p>
                            <button
                              type="button"
                              className={styles.buttonGhost}
                              onClick={() => removeTimeBlockMutation.mutate(block.block_id)}
                              disabled={removeTimeBlockMutation.isPending}
                            >
                              Удалить
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className={styles.softText}>Исключения пока не добавлены.</p>
                    )}
                  </div>
                ) : null}
              </section>
            </div>
          </section>
        ) : (
          <section className={styles.content}>
            <h2>{currentTab.title}</h2>
            <p className={styles.softText}>{currentTab.subtitle}</p>
          </section>
        )}

        <nav className={styles.bottomNav}>
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={item.key === currentTab.key ? styles.navItemActive : styles.navItem}
              onClick={() => setActiveTabKey(item.key)}
            >
              {item.title}
            </button>
          ))}
        </nav>
        {canSwitchMode ? (
          <div className={styles.bottomModeSwitch}>
            {resolvedMode === "client" ? (
              <button
                type="button"
                className={styles.adminAccessButton}
                onClick={() => modeSwitchMutation.mutate("admin")}
              >
                Админские настройки
              </button>
            ) : (
              <button
                type="button"
                className={styles.adminAccessButton}
                onClick={() => modeSwitchMutation.mutate("client")}
              >
                Вернуться на главную
              </button>
            )}
          </div>
        ) : null}
      </section>
      {newBookingOpen && resolvedMode === "client" ? (
        <NewBookingFlow initData={initData} onClose={() => setNewBookingOpen(false)} />
      ) : null}
      {cancelDialog ? (
        <div className={styles.rescheduleOverlay}>
          <section className={styles.rescheduleModal}>
            <div className={styles.rescheduleHeader}>
              <h3>Отмена заявки</h3>
              <button
                type="button"
                className={styles.buttonGhost}
                onClick={() => setCancelDialog(null)}
                disabled={cancelBookingMutation.isPending}
              >
                Закрыть
              </button>
            </div>
            <p className={styles.softText}>Тема: {cancelDialog.topic}</p>
            <label className={styles.field}>
              <span>Комментарий к отмене (необязательно)</span>
              <textarea
                value={cancelDialog.comment}
                onChange={(event) =>
                  setCancelDialog((prev) =>
                    prev
                      ? {
                          ...prev,
                          comment: event.target.value
                        }
                      : prev
                  )
                }
                disabled={cancelBookingMutation.isPending}
              />
            </label>
            {cancelDialog.error ? <p className={styles.errorText}>{cancelDialog.error}</p> : null}
            <div className={styles.cardActionsCenter}>
              <button
                type="button"
                className={styles.buttonGhost}
                onClick={() => cancelBookingMutation.mutate(cancelDialog.bookingId)}
                disabled={cancelBookingMutation.isPending}
              >
                Отменить заявку
              </button>
            </div>
          </section>
        </div>
      ) : null}
      {isAdminRequestsTab && selectedAdminBookingId !== null ? (
        <div className={styles.rescheduleOverlay}>
          <section className={styles.rescheduleModal}>
            <div className={styles.rescheduleHeader}>
              <h3>{adminBookingCardQuery.data?.topic || "Карточка заявки"}</h3>
              <button
                type="button"
                className={styles.buttonGhost}
                onClick={() => setSelectedAdminBookingId(null)}
              >
                Закрыть
              </button>
            </div>

            {adminBookingCardQuery.isPending ? <p className={styles.softText}>Открываем карточку заявки...</p> : null}
            {adminBookingCardQuery.isError ? (
              <p className={styles.errorText}>Не удалось загрузить карточку заявки.</p>
            ) : null}

            {adminBookingCardQuery.data ? (
              <>
                <p className={styles.softText}>
                  Статус: {statusLabelForCard(adminBookingCardQuery.data.status, adminBookingCardQuery.data.slot_end_at)}
                </p>
                <p className={styles.softText}>
                  Клиент: {formatAdminClientName(adminBookingCardQuery.data.user)}
                </p>
                <p className={styles.softText}>
                  Telegram: {formatTelegramUsername(adminBookingCardQuery.data.user.telegram_username)}
                </p>
                <p className={styles.softText}>
                  Контакты:{" "}
                  {[adminBookingCardQuery.data.user.email, adminBookingCardQuery.data.user.phone]
                    .filter(Boolean)
                    .join(" • ") || "не указаны"}
                </p>
                <p className={styles.softText}>
                  Текущее время: {formatSlot(adminBookingCardQuery.data.slot_start_at, adminBookingCardQuery.data.slot_end_at)}
                </p>
                {adminBookingCardQuery.data.requested_new_slot_start_at ? (
                  <p className={styles.softText}>
                    Запрошен перенос:{" "}
                    {formatSlot(
                      adminBookingCardQuery.data.requested_new_slot_start_at,
                      adminBookingCardQuery.data.requested_new_slot_end_at
                    )}
                  </p>
                ) : null}

                <label className={styles.field}>
                  <span>Комментарий для клиента</span>
                  <textarea
                    value={adminMetaForm.admin_public_comment}
                    onChange={(event) =>
                      setAdminMetaForm((prev) => ({
                        ...prev,
                        admin_public_comment: event.target.value
                      }))
                    }
                  />
                </label>
                <label className={styles.field}>
                  <span>Ссылка на встречу</span>
                  <input
                    value={adminMetaForm.meeting_link}
                    onChange={(event) =>
                      setAdminMetaForm((prev) => ({
                        ...prev,
                        meeting_link: event.target.value
                      }))
                    }
                    placeholder="https://..."
                  />
                </label>
                {adminBookingCardQuery.data.status === "pending_decision" ||
                adminBookingCardQuery.data.status === "reschedule_requested" ? (
                  <>
                    <div className={styles.cardActionsCenter}>
                      <button
                        type="button"
                        className={styles.primaryCta}
                        onClick={() =>
                          confirmAdminMutation.mutate({
                            bookingId: adminBookingCardQuery.data.booking_id,
                            payload: toAdminDecisionPayload()
                          })
                        }
                        disabled={confirmAdminMutation.isPending || rejectAdminMutation.isPending}
                      >
                        Подтвердить
                      </button>
                    </div>
                    <div className={styles.cardActionsCenter}>
                      <button
                        type="button"
                        className={styles.buttonGhost}
                        onClick={() =>
                          rejectAdminMutation.mutate({
                            bookingId: adminBookingCardQuery.data.booking_id,
                            payload: toAdminDecisionPayload()
                          })
                        }
                        disabled={confirmAdminMutation.isPending || rejectAdminMutation.isPending}
                      >
                        Отклонить
                      </button>
                    </div>
                  </>
                ) : (
                  <p className={styles.softText}>Для этого статуса действия подтверждения не требуются.</p>
                )}
              </>
            ) : null}
          </section>
        </div>
      ) : null}
      {rescheduleState ? (
        <div className={styles.rescheduleOverlay}>
          <section className={styles.rescheduleModal}>
            <div className={styles.rescheduleHeader}>
              <h3>Перенос заявки</h3>
              <button
                type="button"
                className={styles.buttonGhost}
                onClick={() => {
                  setRescheduleState(null);
                  setRescheduleError("");
                }}
              >
                Закрыть
              </button>
            </div>
            <p className={styles.softText}>Тема встречи: {rescheduleState.topic}</p>
            <p className={styles.softText}>Текущий слот: {rescheduleState.currentSlotLabel}</p>
            <p className={styles.softText}>Выберите новое время, на которое хотите перенести встречу.</p>
            {rescheduleError ? <p className={styles.errorText}>{rescheduleError}</p> : null}
            <div className={styles.weekNav}>
              <button
                type="button"
                className={styles.buttonGhost}
                onClick={() => {
                  const index = rescheduleState.slotsData.week_options.findIndex(
                    (option) => option.key === rescheduleState.selectedWeek
                  );
                  if (index <= 0) {
                    return;
                  }
                  const weekKey = rescheduleState.slotsData.week_options[index - 1].key;
                  const dayKey = rescheduleState.slotsData.day_options_by_week[weekKey]?.[0]?.key ?? "";
                  setRescheduleState((prev) =>
                    prev
                      ? {
                          ...prev,
                          selectedWeek: weekKey,
                          selectedDay: dayKey,
                          selectedSlot: prev.slotsData.time_options_by_day[dayKey]?.[0] ?? null
                        }
                      : prev
                  );
                }}
              >
                ←
              </button>
              <p className={styles.weekLabel}>
                {rescheduleState.selectedWeek ? formatWeekLabel(rescheduleState.selectedWeek) : "Неделя"}
              </p>
              <button
                type="button"
                className={styles.buttonGhost}
                onClick={() => {
                  const index = rescheduleState.slotsData.week_options.findIndex(
                    (option) => option.key === rescheduleState.selectedWeek
                  );
                  if (index < 0 || index >= rescheduleState.slotsData.week_options.length - 1) {
                    return;
                  }
                  const weekKey = rescheduleState.slotsData.week_options[index + 1].key;
                  const dayKey = rescheduleState.slotsData.day_options_by_week[weekKey]?.[0]?.key ?? "";
                  setRescheduleState((prev) =>
                    prev
                      ? {
                          ...prev,
                          selectedWeek: weekKey,
                          selectedDay: dayKey,
                          selectedSlot: prev.slotsData.time_options_by_day[dayKey]?.[0] ?? null
                        }
                      : prev
                  );
                }}
              >
                →
              </button>
            </div>
            <div className={styles.cardActions}>
              {(rescheduleState.slotsData.day_options_by_week[rescheduleState.selectedWeek] ?? []).map((day) => (
                <button
                  key={day.key}
                  type="button"
                  className={day.key === rescheduleState.selectedDay ? styles.button : styles.buttonGhost}
                  onClick={() => {
                    setRescheduleState((prev) =>
                      prev
                        ? {
                            ...prev,
                            selectedDay: day.key,
                            selectedSlot: prev.slotsData.time_options_by_day[day.key]?.[0] ?? null
                          }
                        : prev
                    );
                  }}
                >
                  {new Intl.DateTimeFormat("ru-RU", {
                    day: "numeric",
                    month: "long",
                    weekday: "long"
                  }).format(new Date(day.key))}
                </button>
              ))}
            </div>
            <div className={styles.cardActions}>
              {(rescheduleState.slotsData.time_options_by_day[rescheduleState.selectedDay] ?? []).map((slot) => (
                <button
                  key={slot.slot_key}
                  type="button"
                  className={rescheduleState.selectedSlot?.slot_key === slot.slot_key ? styles.button : styles.buttonGhost}
                  onClick={() => setRescheduleState((prev) => (prev ? { ...prev, selectedSlot: slot } : prev))}
                >
                  {slot.label}
                </button>
              ))}
            </div>
            <div className={styles.cardActionsCenter}>
              <button
                type="button"
                className={`${styles.primaryCta} ${styles.centeredButton}`}
                onClick={() => submitRescheduleMutation.mutate()}
                disabled={!rescheduleState.selectedSlot || submitRescheduleMutation.isPending}
              >
                Отправить запрос
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
