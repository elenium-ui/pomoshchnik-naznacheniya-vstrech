import { useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import { useMutation } from "@tanstack/react-query";

import {
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

export function NewBookingFlow({ initData, onClose }: Props) {
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

  const startMutation = useMutation({
    mutationFn: () => startBookingSession(initData),
    onSuccess: (payload) => {
      setBookingId(payload.booking_id);
      setForm((prev) => ({
        ...prev,
        name: payload.profile.name ?? "",
        email: payload.profile.email ?? "",
        phone: payload.profile.phone ?? ""
      }));
      setUsernameExists(Boolean(payload.profile.telegram_username));
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

  useEffect(() => {
    startMutation.mutate();
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

  const phoneRequired = !usernameExists && form.email.trim().length === 0;
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
    if (step === 8) {
      await submitMutation.mutateAsync();
      return;
    }
    setStep((prev) => Math.min(prev + 1, 8));
  }

  function goBack() {
    setStep((prev) => Math.max(prev - 1, 1));
  }

  if (startMutation.isPending) {
    return <div className={styles.overlay}>Подготавливаем форму новой заявки...</div>;
  }
  if (startMutation.isError) {
    return (
      <div className={styles.overlay}>
        <div className={styles.errorBox}>
          <p>{startMutation.error.message}</p>
          <button type="button" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.overlay}>
      <section className={styles.panel}>
        <header className={styles.header}>
          <h2>Новая заявка</h2>
          <button type="button" onClick={onClose} className={styles.closeButton}>
            Закрыть
          </button>
        </header>

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
          <label className={styles.field}>
            <span>Тема встречи</span>
            <input
              value={form.topic}
              onChange={(event) => setForm((prev) => ({ ...prev, topic: event.target.value }))}
              placeholder="Например: управленческий учёт"
            />
          </label>
        ) : null}

        {step === 3 ? (
          <div className={styles.segment}>
            <p>Формат встречи</p>
            <div className={styles.row}>
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
            <p>Длительность</p>
            <div className={styles.rowWrap}>
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
          <div className={styles.segment}>
            <label className={styles.field}>
              <span>Неделя</span>
              <select value={selectedWeek} onChange={(event) => setSelectedWeek(event.target.value)}>
                {slotsData?.week_options.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>День</span>
              <select value={selectedDay} onChange={(event) => setSelectedDay(event.target.value)}>
                {(slotsData?.day_options_by_week[selectedWeek] ?? []).map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className={styles.rowWrap}>
              {currentSlots.map((slot) => (
                <button
                  key={slot.slot_key}
                  type="button"
                  className={selectedSlot?.slot_key === slot.slot_key ? styles.active : styles.passive}
                  onClick={() => setSelectedSlot(slot)}
                >
                  {slot.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {step === 8 ? (
          <div className={styles.segment}>
            <p className={styles.summaryLine}>Имя: {form.name}</p>
            <p className={styles.summaryLine}>Тема: {form.topic}</p>
            <p className={styles.summaryLine}>Формат: {form.meetingFormat}</p>
            <p className={styles.summaryLine}>Длительность: {form.durationMinutes} мин</p>
            <p className={styles.summaryLine}>
              Слот:{" "}
              {selectedSlot
                ? `${dayjs(selectedSlot.starts_at).format("DD.MM HH:mm")} - ${dayjs(
                    selectedSlot.ends_at
                  ).format("HH:mm")}`
                : "не выбран"}
            </p>
          </div>
        ) : null}

        {step === 9 && submitted ? (
          <div className={styles.segment}>
            <h3>Заявка отправлена</h3>
            <p className={styles.summaryLine}>Статус: {submitted.status}</p>
            <p className={styles.summaryLine}>
              Слот: {dayjs(submitted.slot_start_at).format("DD.MM HH:mm")} -{" "}
              {dayjs(submitted.slot_end_at).format("HH:mm")}
            </p>
          </div>
        ) : null}

        <footer className={styles.footer}>
          {step > 1 && step <= 8 ? (
            <button type="button" onClick={goBack} className={styles.ghostButton}>
              Назад
            </button>
          ) : null}
          {step <= 8 ? (
            <button
              type="button"
              onClick={() => void goNext()}
              className={styles.mainButton}
              disabled={
                !canGoNext ||
                saveDraftMutation.isPending ||
                slotsMutation.isPending ||
                submitMutation.isPending
              }
            >
              {step === 8 ? "Подтвердить и отправить" : "Далее"}
            </button>
          ) : (
            <button type="button" onClick={onClose} className={styles.mainButton}>
              Закрыть
            </button>
          )}
        </footer>

        {saveDraftMutation.isError ? <p className={styles.errorText}>{saveDraftMutation.error.message}</p> : null}
        {slotsMutation.isError ? <p className={styles.errorText}>{slotsMutation.error.message}</p> : null}
        {submitMutation.isError ? <p className={styles.errorText}>{submitMutation.error.message}</p> : null}
      </section>
    </div>
  );
}

