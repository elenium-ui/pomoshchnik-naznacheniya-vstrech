import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { createAuthSession, switchAuthMode } from "../api/miniapp";
import type { AuthSessionResponse, ModeName } from "../api/types";
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

export function AppShellPage() {
  const initData = useMemo(() => getTelegramInitData(), []);
  const [currentMode, setCurrentMode] = useState<ModeName | null>(null);
  const [activeTabKey, setActiveTabKey] = useState<string>("home");

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
  const canSwitchMode = authPayload.access.is_admin;
  const isProfileTab = currentTab.key === "profile";

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <header className={styles.header}>
          <div className={styles.brand}>ER Meet</div>
          <p className={styles.brandSub}>запись на встречу</p>
          <h1>Запись на встречу с Еленой</h1>
          <p className={styles.lead}>
            Вы попали в пространство записи к Елене Разумовой. Здесь можно выбрать удобное время,
            отправить заявку на встречу и отслеживать её статус.
          </p>
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
            <h2>Здравствуйте, {getFirstName(authPayload)}.</h2>
            <p className={styles.softText}>
              {resolvedMode === "admin"
                ? "Вы в админском режиме. Здесь будет центр управления заявками и расписанием."
                : "Здесь можно выбрать время, отправить заявку и отслеживать её статус."}
            </p>
            <div className={styles.featureCard}>
              <h3>Чем могу быть полезна</h3>
              <ul>
                <li>Финансовые задачи и рабочие вопросы</li>
                <li>Управленческий учёт и структурирование процессов</li>
                <li>Вайб-кодинг, идеи, знакомство и спокойное живое общение</li>
              </ul>
            </div>
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
    </main>
  );
}
