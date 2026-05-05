import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelClientBooking,
  createAuthSession,
  loadClientActiveBookings,
  loadClientHistoryBookings,
  loadClientProfile,
  startClientReschedule,
  switchAuthMode,
  updateClientProfile
} from "../api/miniapp";
import type { AuthSessionResponse, ClientBookingItem, ModeName } from "../api/types";
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

export function AppShellPage() {
  const initData = useMemo(() => getTelegramInitData(), []);
  const queryClient = useQueryClient();
  const [currentMode, setCurrentMode] = useState<ModeName | null>(null);
  const [activeTabKey, setActiveTabKey] = useState<string>("home");
  const [newBookingOpen, setNewBookingOpen] = useState(false);
  const [actionMessage, setActionMessage] = useState<string>("");
  const [profileForm, setProfileForm] = useState({
    name: "",
    email: "",
    phone: ""
  });

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

  const cancelBookingMutation = useMutation({
    mutationFn: (bookingId: number) => cancelClientBooking(bookingId, initData),
    onSuccess: (payload) => {
      setActionMessage(payload.message);
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-active-bookings", initData] });
      void queryClient.invalidateQueries({ queryKey: ["miniapp-client-history-bookings", initData] });
    }
  });

  const startRescheduleMutation = useMutation({
    mutationFn: (bookingId: number) => startClientReschedule(bookingId, initData),
    onSuccess: (payload) => {
      setActionMessage(`${payload.message} Найдено слотов: ${payload.available_slots.total_slots}.`);
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
  const isProfileTab = currentTab.key === "profile";
  const isClientCabinetTab = resolvedMode === "client" && currentTab.key !== "home";

  function renderBookingCard(item: ClientBookingItem, showActions: boolean) {
    return (
      <article key={item.booking_id} className={styles.bookingCard}>
        <h3>{item.topic || "Заявка без темы"}</h3>
        <p className={styles.softText}>Статус: {statusLabel(item.status)}</p>
        <p className={styles.softText}>Время: {formatSlot(item.slot_start_at, item.slot_end_at)}</p>
        <p className={styles.softText}>
          Формат: {item.meeting_format || "не указан"} • Длительность: {item.duration_minutes || "—"} мин
        </p>
        {item.comment ? <p className={styles.softText}>Комментарий: {item.comment}</p> : null}
        {showActions ? (
          <div className={styles.cardActions}>
            <button
              type="button"
              className={styles.buttonGhost}
              onClick={() => cancelBookingMutation.mutate(item.booking_id)}
              disabled={cancelBookingMutation.isPending}
            >
              Отменить
            </button>
            <button
              type="button"
              className={styles.button}
              onClick={() => startRescheduleMutation.mutate(item.booking_id)}
              disabled={startRescheduleMutation.isPending}
            >
              Перенести
            </button>
          </div>
        ) : null}
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
              <div className={styles.photoPlaceholder} aria-hidden="true">
                Фото
              </div>
            </div>
          ) : (
            <>
              <div className={styles.brand}>ER Meet</div>
              <h1>Запись на встречу с Еленой</h1>
            </>
          )}
          {canSwitchMode ? (
            <div className={styles.modeSwitch}>
              <button
                type="button"
                className={resolvedMode === "admin" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => modeSwitchMutation.mutate("admin")}
              >
                Админ
              </button>
              <button
                type="button"
                className={resolvedMode === "client" ? styles.modeButtonActive : styles.modeButton}
                onClick={() => modeSwitchMutation.mutate("client")}
              >
                Клиент
              </button>
            </div>
          ) : null}
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
              <h2 className={styles.centeredTitle}>Здравствуйте, {getFirstName(authPayload)}.</h2>
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
                {activeBookingsQuery.isPending ? <p className={styles.softText}>Загружаем активные заявки...</p> : null}
                {activeBookingsQuery.isError ? (
                  <p className={styles.errorText}>Не удалось загрузить активные заявки.</p>
                ) : null}
                {activeBookingsQuery.data?.items.length ? (
                  activeBookingsQuery.data.items.map((item) => renderBookingCard(item, true))
                ) : (
                  <p className={styles.softText}>Активных заявок пока нет.</p>
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
                  className={styles.primaryCta}
                  onClick={() => updateProfileMutation.mutate()}
                  disabled={updateProfileMutation.isPending || profileQuery.isPending}
                >
                  Сохранить профиль
                </button>
              </div>
            ) : null}
          </section>
        ) : (
          <section className={styles.content}>
            <h2>{currentTab.title}</h2>
            <p className={styles.softText}>{currentTab.subtitle}</p>
            {isProfileTab && canSwitchMode ? (
              <div className={styles.inlinePanel}>
                <p>Быстрое переключение режима</p>
                <div className={styles.modeSwitch}>
                  <button
                    type="button"
                    className={resolvedMode === "admin" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => modeSwitchMutation.mutate("admin")}
                  >
                    Админ
                  </button>
                  <button
                    type="button"
                    className={resolvedMode === "client" ? styles.modeButtonActive : styles.modeButton}
                    onClick={() => modeSwitchMutation.mutate("client")}
                  >
                    Клиент
                  </button>
                </div>
              </div>
            ) : null}
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
      </section>
      {newBookingOpen && resolvedMode === "client" ? (
        <NewBookingFlow initData={initData} onClose={() => setNewBookingOpen(false)} />
      ) : null}
    </main>
  );
}
