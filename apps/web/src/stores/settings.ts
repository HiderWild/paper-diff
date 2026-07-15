import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { setLocale, type AppLocale } from "../i18n";

export type ThemeMode = "system" | "dark" | "light";

const KEY = "paper-diff-settings-v1";

export type SettingsState = {
  theme: ThemeMode;
  locale: AppLocale;
  /** When true, hide empty panes after last tool closes (reserved) */
  compactWorkbench: boolean;
  showToolTips: boolean;
  /** Default ON: flush dirty work files after idle */
  autoSave: boolean;
};

const DEFAULTS: SettingsState = {
  theme: "system",
  locale: "zh-CN",
  compactWorkbench: false,
  showToolTips: true,
  autoSave: true,
};

function load(): SettingsState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) {
      // migrate locale from legacy key
      let locale: AppLocale = "zh-CN";
      try {
        const l = localStorage.getItem("paper-diff-locale");
        if (l === "zh-CN" || l === "en") locale = l;
      } catch {
        /* ignore */
      }
      return { ...DEFAULTS, locale };
    }
    const parsed = { ...DEFAULTS, ...JSON.parse(raw) } as SettingsState;
    if (parsed.theme !== "system" && parsed.theme !== "dark" && parsed.theme !== "light") {
      parsed.theme = "system";
    }
    if (parsed.locale !== "zh-CN" && parsed.locale !== "en") {
      parsed.locale = "zh-CN";
    }
    if (typeof parsed.autoSave !== "boolean") parsed.autoSave = true;
    return parsed;
  } catch {
    return { ...DEFAULTS };
  }
}

function resolveTheme(mode: ThemeMode): "dark" | "light" {
  if (mode === "dark" || mode === "light") return mode;
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }
  return "dark";
}

export function applyThemeToDocument(mode: ThemeMode) {
  if (typeof document === "undefined") return;
  const resolved = resolveTheme(mode);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export const useSettingsStore = defineStore("settings", () => {
  const initial = load();
  const theme = ref<ThemeMode>(initial.theme);
  const locale = ref<AppLocale>(initial.locale);
  const compactWorkbench = ref(initial.compactWorkbench);
  const showToolTips = ref(initial.showToolTips);
  const autoSave = ref(initial.autoSave !== false);

  const resolvedTheme = computed(() => resolveTheme(theme.value));
  const monacoTheme = computed(() =>
    resolvedTheme.value === "light" ? "vs" : "vs-dark"
  );

  function persist() {
    const s: SettingsState = {
      theme: theme.value,
      locale: locale.value,
      compactWorkbench: compactWorkbench.value,
      showToolTips: showToolTips.value,
      autoSave: autoSave.value,
    };
    try {
      localStorage.setItem(KEY, JSON.stringify(s));
    } catch {
      /* ignore */
    }
  }

  function setTheme(mode: ThemeMode) {
    theme.value = mode;
    applyThemeToDocument(mode);
  }

  function setAppLocale(l: AppLocale) {
    locale.value = l;
    setLocale(l);
  }

  function init() {
    setLocale(locale.value);
    applyThemeToDocument(theme.value);
    if (typeof window !== "undefined" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: light)");
      const onChange = () => {
        if (theme.value === "system") applyThemeToDocument("system");
      };
      mq.addEventListener?.("change", onChange);
    }
  }

  watch([theme, locale, compactWorkbench, showToolTips, autoSave], persist, {
    deep: true,
  });

  // apply on store creation
  applyThemeToDocument(theme.value);

  return {
    theme,
    locale,
    compactWorkbench,
    showToolTips,
    autoSave,
    resolvedTheme,
    monacoTheme,
    setTheme,
    setAppLocale,
    init,
    persist,
  };
});
