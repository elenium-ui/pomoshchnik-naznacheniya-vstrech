type TelegramWebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  close?: () => void;
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

function readInitDataFromQuery(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("tgInitData") ?? "";
}

function readInitDataFromHash(): string {
  const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash;
  if (!hash) {
    return "";
  }
  const params = new URLSearchParams(hash);
  const raw = params.get("tgWebAppData");
  if (!raw) {
    return "";
  }
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function getTelegramInitData(): string {
  const webApp = getTelegramWebApp();
  if (webApp?.initData) {
    return webApp.initData;
  }
  return readInitDataFromQuery() || readInitDataFromHash();
}
