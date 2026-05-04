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

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function getTelegramInitData(): string {
  const webApp = getTelegramWebApp();
  if (webApp?.initData) {
    return webApp.initData;
  }
  return readInitDataFromQuery();
}

