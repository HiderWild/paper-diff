import { createI18n } from "vue-i18n";
import zhCN from "./locales/zh-CN";
import en from "./locales/en";

export type AppLocale = "zh-CN" | "en";

export const LOCALE_STORAGE_KEY = "paper-diff-locale";

const messages = {
  "zh-CN": zhCN,
  en,
} as const;

function readStoredLocale(): AppLocale {
  try {
    const v = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (v === "zh-CN" || v === "en") return v;
  } catch {
    /* ignore */
  }
  return "zh-CN";
}

export function setDocumentLang(locale: AppLocale) {
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale === "zh-CN" ? "zh-CN" : "en";
  }
}

const initial = readStoredLocale();
setDocumentLang(initial);

export const i18n = createI18n({
  legacy: false,
  locale: initial,
  fallbackLocale: "en",
  messages,
});

export function setLocale(locale: AppLocale) {
  i18n.global.locale.value = locale;
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    /* ignore */
  }
  setDocumentLang(locale);
}

export default i18n;
