import { useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import "dayjs/locale/ru";
import { useMutation } from "@tanstack/react-query";

import {
  joinBookingWaitlist,
  loadBookingSlots,
  saveBookingDraft,
  startBookingSession,
  submitBooking
} from "../../api/miniapp";
import type { BookingSlotsResponse, SlotTimeOption, SubmittedBookingPayload } from "../../api/types";
import styles from "./NewBookingFlow.module.scss";

type Props = {
  initData: string;
  onClose: () => void;
  startMode?: "resume" | "new";
  onDraftSaved?: () => void;
};

type FormState = {
  name: string;
  topic: string;
  meetingFormat: "онлайн" | "офлайн";
  durationMinutes: 15 | 30 | 45 | 60 | 90;
  email: string;
  phone: string;
  comment: string;
};

const durationOptions: Array<15 | 30 | 45 | 60 | 90> = [15, 30, 45, 60, 90];
dayjs.locale("ru");

function capitalize(text: string): string {
  return text.length ? text[0].toUpperCase() + text.slice(1) : text;
}

function formatWeekLabel(weekKey: string): string {
  const start = dayjs(weekKey);
  const end = start.add(6, "day");
  const sameYear = start.year() === end.year();
  return sameYear
    ? `${start.format("D MMMM")} - ${end.format("D MMMM")} ${start.format("YYYY")} года`
    : `${start.format("D MMMM YYYY")} - ${end.format("D MMMM YYYY")}`;
}

function formatDayLabel(dayKey: string): string {
  const date = dayjs(dayKey);
  return `${date.format("D MMMM")}, ${capitalize(date.format("dddd"))}`;
}

function formatSlotRange(startAt: string, endAt: string): string {
  const start = dayjs(startAt);
  const end = dayjs(endAt);
  return `${start.format("D MMMM")}, ${capitalize(start.format("dddd"))} ${start.format("HH:mm")} - ${end.format("HH:mm")}`;
}

export function NewBookingFlow({ initData, onClose, startMode = "resume", onDraftSaved }: Props) {
  const [bookingId, setBookingId] = useState<number | null>(null);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormState>({
    name: "",
    topic: "",
    meetingFormat: "онлайн",
    durationMinutes: 30,
    email: "",
    phone: "",
    comment: ""
  });
  const [usernameExists, setUsernameExists] = useState(true);
  const [slotsData, setSlotsData] = useState<BookingSlotsResponse | null>(null);
  const [selectedWeek, setSelectedWeek] = useState<string>("");
  const [selectedDay, setSelectedDay] = useState<string>("");
  const [selectedSlot, setSelectedSlot] = useState<SlotTimeOption | null>(null);
  const [submitted, setSubmitted] = useState<SubmittedBookingPayload | null>(null);
  const [waitlistDate, setWaitlistDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [waitlistComment, setWaitlistComment] = useState("");
  const [submissionTarget, setSubmissionTarget] = useState<"slot" | "waitlist">("slot");
  const [waitlistPanelOpen, setWaitlistPanelOpen] = useState(false);

  const startMutation = useMutation({
    mutationFn: ({ startOver }: { startOver: boolean }) =>
      startBookingSession(initData, { start_over: startOver }),
    onSuccess: (payload) => {
      setBookingId(payload.booking_id);
      setForm((prev) => ({
        ...prev,
        name: payload.profile.name ?? "",
        email: payload.profile.email ?? "",
        phone: payload.profile.phone ?? ""
      }));
      setUsernameExists(Boolean(payload.profile.telegram_username));
      if (payload.has_active_draft && payload.active_draft) {
        setForm((prev) => ({
          ...prev,
          topic: payload.active_draft?.topic ?? "",
          meetingFormat: payload.active_draft?.meeting_format === "офлайн" ? "офлайн" : "онлайн",
          durationMinutes: (payload.active_draft?.duration_minutes as 15 | 30 | 45 | 60 | 90 | null) ?? prev.durationMinutes,
          email: payload.active_draft?.email ?? prev.email,
          phone: payload.active_draft?.phone ?? prev.phone,
          comment: payload.active_draft?.comment ?? ""
        }));
      }
    }
  });

  const saveDraftMutation = useMutation({
    mutationFn: async () => {
      if (!bookingId) {
        throw new Error("Draft is not initialized.");
      }
      return saveBookingDraft(bookingId, {
        init_data: initData,
        name: form.name,
        topic: form.topic,
        meeting_format: form.meetingFormat,
        duration_minutes: form.durationMinutes,
        email: form.email || null,
        phone: form.phone || null,
        comment: form.comment || null
      });
    }
  });

  const slotsMutation = useMutation({
    mutationFn: () => loadBookingSlots(initData, form.durationMinutes),
    onSuccess: (payload) => {
      setSlotsData(payload);
      setSubmissionTarget("slot");
      const firstWeek = payload.week_options[0]?.key ?? "";
      setSelectedWeek(firstWeek);
      const firstDay = payload.day_options_by_week[firstWeek]?.[0]?.key ?? "";
      setSelectedDay(firstDay);
      const firstSlot = payload.time_options_by_day[firstDay]?.[0] ?? null;
      setSelectedSlot(firstSlot);
    }
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!bookingId || !selectedSlot) {
        throw new Error("Slot is not selected.");
      }
      return submitBooking(bookingId, initData, selectedSlot.slot_key);
    },
    onSuccess: (payload) => {
      setSubmitted(payload);
      setStep(9);
    }
  });

  const joinWaitlistMutation = useMutation({
    mutationFn: async () => {
      if (!bookingId) {
        throw new Error("Draft is not initialized.");
      }
      const effectiveWaitlistComment = waitlistComment.trim() || form.comment.trim();
      return joinBookingWaitlist(bookingId, initData, waitlistDate, effectiveWaitlistComment);
    },
    onSuccess: () => {
      setSubmitted(null);
      setStep(9);
    }
  });

  useEffect(() => {
    startMutation.mutate({ startOver: startMode === "new" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!slotsData || !selectedWeek) {
      return;
    }
    const candidateDay = slotsData.day_options_by_week[selectedWeek]?.[0]?.key ?? "";
    setSelectedDay(candidateDay);
    const candidateSlot = slotsData.time_options_by_day[candidateDay]?.[0] ?? null;
    setSelectedSlot(candidateSlot);
  }, [slotsData, selectedWeek]);

  useEffect(() => {
    if (!slotsData || !selectedDay) {
      return;
    }
    const candidateSlot = slotsData.time_options_by_day[selectedDay]?.[0] ?? null;
    setSelectedSlot(candidateSlot);
  }, [slotsData, selectedDay]);

  const currentSlots = useMemo(
    () => (selectedDay && slotsData ? slotsData.time_options_by_day[selectedDay] ?? [] : []),
    [selectedDay, slotsData]
  );
  const selectedWeekDays = useMemo(
    () => (selectedWeek && slotsData ? slotsData.day_options_by_week[selectedWeek] ?? [] : []),
    [selectedWeek, slotsData]
  );
  const weekOptions = slotsData?.week_options ?? [];
  const hasAvailableSlots = Boolean(slotsData && slotsData.total_slots > 0);
  const selectedWeekIndex = Math.max(
    0,
    weekOptions.findIndex((option) => option.key === selectedWeek)
  );
  const bookingTitle =
    form.topic.trim().length >= 3 ? `Тема встречи: ${form.topic.trim()}` : "Новая заявка";

  useEffect(() => {
    if (step !== 7) {
      return;
    }
    if (!hasAvailableSlots) {
      setWaitlistPanelOpen(true);
    }
  }, [step, hasAvailableSlots]);

  const phoneRequired = !usernameExists && form.email.trim().length === 0;
  const canSaveDraft =
    Boolean(bookingId) &&
    form.name.trim().length >= 2 &&
    form.topic.trim().length >= 3 &&
    form.durationMinutes > 0;
  const canGoNext =
    (step === 1 && form.name.trim().length >= 2) ||
    (step === 2 && form.topic.trim().length >= 3) ||
    step === 3 ||
    step === 4 ||
    (step === 5 && (!phoneRequired || form.phone.trim().length >= 6)) ||
    step === 6 ||
    (step === 7 && Boolean(selectedSlot)) ||
    step === 8;

  async function goNext() {
    if (!canGoNext) {
      return;
    }
    if (step === 6) {
      await saveDraftMutation.mutateAsync();
      await slotsMutation.mutateAsync();
      setStep(7);
      return;
    }
    if (step === 7) {
      setSubmissionTarget("slot");
    }
    if (step === 8) {
      if (submissionTarget === "waitlist") {
        await joinWaitlistMutation.mutateAsync();
        return;
      }
      await submitMutation.mutateAsync();
      return;
    }
    setStep((prev) => Math.min(prev + 1, 8));
  }

  async function saveDraftAndExit() {
    try {
      await saveDraftMutation.mutateAsync();
      onDraftSaved?.();
      onClose();
    } catch {
      // Error is displayed by mutation state below.
    }
  }

  function goBack() {
    setStep((prev) => Math.max(prev - 1, 1));
  }

  function switchWeek(offset: -1 | 1) {
    if (!weekOptions.length) {
      return;
    }
    const candidateIndex = selectedWeekIndex + offset;
    if (candidateIndex < 0 || candidateIndex >= weekOptions.length) {
      return;
    }
    setSelectedWeek(weekOptions[candidateIndex].key);
  }

  function goToWaitlistConfirmation() {
    if (!waitlistComment.trim() && form.comment.trim()) {
      setWaitlistComment(form.comment.trim());
    }
    setSubmissionTarget("waitlist");
    setStep(8);
  }

  const isWaitlistCompactActions = step === 7 && waitlistPanelOpen;

  if (startMutation.isPending) {
    return <div className={styles.overlay}>Подготавливаем форму новой заявки...</div>;
  }
  if (startMutation.isError) {
    return (
      <div className={styles.overlay}>
        <div className={styles.errorBox}>
          <p>{startMutation.error.message}</p>
          <div className={styles.errorActions}>
            <button type="button" onClick={() => startMutation.mutate({ startOver: startMode === "new" })}>
              Попробовать снова
            </button>
            <button type="button" onClick={onClose}>
              Закрыть
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.overlay}>
      <section className={styles.panel}>
        <header className={styles.header}>
          <h2>{bookingTitle}</h2>
          {step <= 8 ? (
            <button type="button" onClick={onClose} className={styles.closeButton}>
              Закрыть
            </button>
          ) : null}
        </header>
        <div className={styles.body}>
          {step <= 8 ? <p className={styles.progress}>Шаг {step} из 8</p> : null}

          {step === 1 ? (
            <label className={styles.field}>
              <span>Имя</span>
              <input
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Введите имя"
              />
            </label>
          ) : null}

          {step === 2 ? (
            <div className={styles.segment}>
              <label className={styles.field}>
                <span>Тема встречи</span>
                <input
                  value={form.topic}
                  onChange={(event) => setForm((prev) => ({ ...prev, topic: event.target.value }))}
                  placeholder="Например: управленческий учёт"
                />
              </label>
            </div>
          ) : null}

          {step === 3 ? (
            <div className={styles.segment}>
              <p className={styles.segmentTitle}>Формат встречи</p>
              <div className={styles.optionColumn}>
                <button
                  type="button"
                  className={form.meetingFormat === "онлайн" ? styles.active : styles.passive}
                  onClick={() => setForm((prev) => ({ ...prev, meetingFormat: "онлайн" }))}
                >
                  Онлайн
                </button>
                <button
                  type="button"
                  className={form.meetingFormat === "офлайн" ? styles.active : styles.passive}
                  onClick={() => setForm((prev) => ({ ...prev, meetingFormat: "офлайн" }))}
                >
                  Офлайн
                </button>
              </div>
            </div>
          ) : null}

          {step === 4 ? (
            <div className={styles.segment}>
              <p className={styles.segmentTitle}>Длительность</p>
              <div className={styles.optionColumn}>
                {durationOptions.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={form.durationMinutes === value ? styles.active : styles.passive}
                    onClick={() =>
                      setForm((prev) => ({
                        ...prev,
                        durationMinutes: value
                      }))
                    }
                  >
                    {value} мин
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {step === 5 ? (
            <div className={styles.segment}>
              <label className={styles.field}>
                <span>Email (необязательно)</span>
                <input
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="you@example.com"
                />
              </label>
              <label className={styles.field}>
                <span>Телефон {phoneRequired ? "(обязателен)" : "(опционально)"}</span>
                <input
                  value={form.phone}
                  onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                  placeholder="+79991234567"
                />
              </label>
            </div>
          ) : null}

          {step === 6 ? (
            <label className={styles.field}>
              <span>Комментарий (необязательно)</span>
              <textarea
                value={form.comment}
                onChange={(event) => setForm((prev) => ({ ...prev, comment: event.target.value }))}
                placeholder="Уточнения по встрече"
              />
            </label>
          ) : null}

          {step === 7 ? (
            <div className={`${styles.segment} ${styles.scheduleSegment}`}>
              {slotsMutation.isPending ? <p className={styles.summaryLine}>Подбираем свободные слоты...</p> : null}
              {hasAvailableSlots ? (
                <>
                  <p className={`${styles.segmentTitle} ${styles.scheduleTitle}`}>Неделя</p>
                  <div className={styles.weekSwitcher}>
                    <button
                      type="button"
                      className={styles.weekArrow}
                      onClick={() => switchWeek(-1)}
                      disabled={selectedWeekIndex <= 0}
                    >
                      ←
                    </button>
                    <div className={styles.weekLabel}>
                      {weekOptions[selectedWeekIndex] ? formatWeekLabel(weekOptions[selectedWeekIndex].key) : "Неделя"}
                    </div>
                    <button
                      type="button"
                      className={styles.weekArrow}
                      onClick={() => switchWeek(1)}
                      disabled={selectedWeekIndex >= weekOptions.length - 1}
                    >
                      →
                    </button>
                  </div>

                  <p className={`${styles.segmentTitle} ${styles.scheduleTitle}`}>День</p>
                  <div className={styles.dayGrid}>
                    {selectedWeekDays.map((option) => (
                      <button
                        key={option.key}
                        type="button"
                        className={`${selectedDay === option.key ? styles.active : styles.passive} ${styles.centeredChip}`}
                        onClick={() => {
                          setSelectedDay(option.key);
                          setSubmissionTarget("slot");
                        }}
                      >
                        {formatDayLabel(option.key)}
                      </button>
                    ))}
                  </div>

                  <p className={`${styles.segmentTitle} ${styles.scheduleTitle}`}>Свободное время</p>
                  <div className={styles.timeGrid}>
                    {currentSlots.map((slot) => (
                      <button
                        key={slot.slot_key}
                        type="button"
                        className={`${selectedSlot?.slot_key === slot.slot_key ? styles.active : styles.passive} ${styles.centeredChip}`}
                        onClick={() => {
                          setSelectedSlot(slot);
                          setSubmissionTarget("slot");
                        }}
                      >
                        {slot.label}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <p className={styles.summaryLine}>
                  На выбранный период сейчас нет свободных слотов.
                </p>
              )}

              <div className={styles.waitlistToggleWrap}>
                <button
                  type="button"
                  className={styles.waitlistToggleButton}
                  onClick={() => setWaitlistPanelOpen((prev) => !prev)}
                >
                  {waitlistPanelOpen ? "Скрыть лист ожидания" : "Не нашли подходящее время?"}
                </button>
              </div>

              {waitlistPanelOpen ? (
                <div className={styles.segment}>
                  <p className={styles.summaryLine}>
                    Вы можете оставить заявку на лист ожидания, если не нашли нужного времени.
                    Эта опция не гарантирует слот на выбранную дату.
                  </p>
                  <label className={styles.field}>
                    <span>Лист ожидания</span>
                    <input
                      type="date"
                      value={waitlistDate}
                      onChange={(event) => setWaitlistDate(event.target.value)}
                    />
                  </label>
                  <label className={styles.field}>
                    <span>Выберите желаемую дату и комментарий для администратора, почему важна именно эта дата или предпочтительное время, которого нет в свободных слотах.</span>
                    <textarea
                      className={styles.compactTextarea}
                      value={waitlistComment}
                      onChange={(event) => setWaitlistComment(event.target.value)}
                      placeholder="Например: важна встреча в этот день после 16:00, другие слоты не подходят."
                    />
                  </label>
                  <button
                    type="button"
                    className={styles.waitlistPrimaryButton}
                    onClick={goToWaitlistConfirmation}
                    disabled={joinWaitlistMutation.isPending || submitMutation.isPending}
                  >
                    Оставить заявку на лист ожидания
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 8 ? (
            <div className={styles.segment}>
              <p className={styles.summaryLine}>Имя: {form.name}</p>
              <p className={styles.summaryLine}>Тема: {form.topic}</p>
              <p className={styles.summaryLine}>Формат: {form.meetingFormat}</p>
              <p className={styles.summaryLine}>Длительность: {form.durationMinutes} мин</p>
              <p className={styles.summaryLine}>Комментарий к заявке: {form.comment.trim() || "не указан"}</p>
              {submissionTarget === "waitlist" ? (
                <>
                  <p className={styles.summaryLine}>
                    Лист ожидания на дату: {dayjs(waitlistDate).format("D MMMM YYYY")}
                  </p>
                  <p className={styles.summaryLine}>
                    Важно: это не гарантирует подтверждение слота, заявка будет рассмотрена администратором.
                  </p>
                  <p className={styles.summaryLine}>
                    Комментарий для листа ожидания: {waitlistComment.trim() || "не указан"}
                  </p>
                </>
              ) : (
                <p className={styles.summaryLine}>
                  Слот:{" "}
                  {selectedSlot
                    ? formatSlotRange(selectedSlot.starts_at, selectedSlot.ends_at)
                    : "не выбран"}
                </p>
              )}
            </div>
          ) : null}

          {step === 9 ? (
            <div className={`${styles.segment} ${styles.successCard}`}>
              <h3>{submitted ? "Заявка отправлена" : "Заявка в листе ожидания"}</h3>
              {submitted ? (
                <>
                  <p className={styles.successText}>Заявка отправлена на согласование. Подтверждение придёт отдельно.</p>
                  {submitted.topic ? <p className={styles.summaryLine}>Тема: {submitted.topic}</p> : null}
                  <p className={styles.summaryLine}>
                    Время встречи: {formatSlotRange(submitted.slot_start_at, submitted.slot_end_at)}
                  </p>
                </>
              ) : (
                <>
                  <p className={styles.successText}>Заявка в лист ожидания отправлена. Сообщим, когда появится слот.</p>
                  <p className={styles.summaryLine}>Дата ожидания: {dayjs(waitlistDate).format("D MMMM YYYY")}</p>
                  <p className={styles.summaryLine}>Тема: {form.topic}</p>
                  <p className={styles.summaryLine}>Комментарий для листа ожидания: {waitlistComment.trim() || "не указан"}</p>
                </>
              )}
            </div>
          ) : null}
        </div>

        <footer className={`${styles.footer} ${isWaitlistCompactActions ? styles.footerCompact : ""}`}>
          {step <= 8 ? (
            <button
              type="button"
              onClick={() => void goNext()}
              className={`${styles.mainButton} ${isWaitlistCompactActions ? styles.compactActionButton : ""}`}
              disabled={
                !canGoNext ||
                (step === 7 && !hasAvailableSlots) ||
                saveDraftMutation.isPending ||
                slotsMutation.isPending ||
                submitMutation.isPending ||
                joinWaitlistMutation.isPending
              }
            >
              {step === 8
                ? submissionTarget === "waitlist"
                  ? "Подтвердить и отправить в лист ожидания"
                  : "Подтвердить и отправить"
                : "Далее"}
            </button>
          ) : (
            <button type="button" onClick={onClose} className={styles.mainButton}>
              Закрыть
            </button>
          )}
          {step <= 8 ? (
            <div className={styles.footerSecondaryRow}>
              {step > 1 ? (
                <button
                  type="button"
                  onClick={goBack}
                  className={`${styles.ghostButton} ${isWaitlistCompactActions ? styles.compactActionButton : ""}`}
                >
                  Назад
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => void saveDraftAndExit()}
                className={`${styles.ghostButton} ${isWaitlistCompactActions ? styles.compactActionButton : ""}`}
                disabled={!canSaveDraft || saveDraftMutation.isPending}
              >
                Сохранить черновик
              </button>
            </div>
          ) : null}
        </footer>

        {saveDraftMutation.isError ? <p className={styles.errorText}>{saveDraftMutation.error.message}</p> : null}
        {slotsMutation.isError ? <p className={styles.errorText}>{slotsMutation.error.message}</p> : null}
        {submitMutation.isError ? <p className={styles.errorText}>{submitMutation.error.message}</p> : null}
        {joinWaitlistMutation.isError ? <p className={styles.errorText}>{joinWaitlistMutation.error.message}</p> : null}
      </section>
    </div>
  );
}
