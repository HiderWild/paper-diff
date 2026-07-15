<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useI18n } from "vue-i18n";
import { useLayoutStore } from "../../stores/layout";
import {
  useSettingsStore,
  type ThemeMode,
} from "../../stores/settings";
import { useWorkbenchStore } from "../../stores/workbench";
import type { AppLocale } from "../../i18n";

defineEmits<{
  hide: [];
}>();

const { t } = useI18n();
const settings = useSettingsStore();
const layout = useLayoutStore();
const workbench = useWorkbenchStore();
const { theme, locale, compactWorkbench, showToolTips, autoSave } =
  storeToRefs(settings);
const { showDotFiles, showFiles } = storeToRefs(layout);

function onTheme(e: Event) {
  settings.setTheme((e.target as HTMLSelectElement).value as ThemeMode);
}

function onLocale(e: Event) {
  settings.setAppLocale((e.target as HTMLSelectElement).value as AppLocale);
}
</script>

<template>
  <div class="settings-panel">
    <div class="panel-header side-header">
      <span>{{ t("settings.title") }}</span>
      <button
        type="button"
        class="header-hide"
        :title="t('toolbar.toggleFiles')"
        @click="$emit('hide')"
      >
        ◀
      </button>
    </div>

    <div class="settings-scroll">
      <section class="settings-section">
        <h4>{{ t("settings.sectionAppearance") }}</h4>
        <label class="settings-row">
          <span>{{ t("settings.theme") }}</span>
          <select :value="theme" @change="onTheme">
            <option value="system">{{ t("settings.themeSystem") }}</option>
            <option value="dark">{{ t("settings.themeDark") }}</option>
            <option value="light">{{ t("settings.themeLight") }}</option>
          </select>
        </label>
        <p class="hint">{{ t("settings.themeHint") }}</p>
      </section>

      <section class="settings-section">
        <h4>{{ t("settings.sectionLanguage") }}</h4>
        <label class="settings-row">
          <span>{{ t("lang.switch") }}</span>
          <select :value="locale" @change="onLocale">
            <option value="zh-CN">{{ t("lang.zh") }}</option>
            <option value="en">{{ t("lang.en") }}</option>
          </select>
        </label>
      </section>

      <section class="settings-section">
        <h4>{{ t("settings.sectionWorkbench") }}</h4>
        <label class="settings-check">
          <input v-model="showFiles" type="checkbox" />
          {{ t("settings.showFiles") }}
        </label>
        <label class="settings-check">
          <input v-model="showDotFiles" type="checkbox" />
          {{ t("tree.showDot") }}
        </label>
        <label class="settings-check">
          <input v-model="showToolTips" type="checkbox" />
          {{ t("settings.showToolTips") }}
        </label>
        <label class="settings-check">
          <input v-model="autoSave" type="checkbox" />
          {{ t("settings.autoSave") }}
        </label>
        <label class="settings-check">
          <input v-model="compactWorkbench" type="checkbox" />
          {{ t("settings.compactWorkbench") }}
        </label>
        <button
          type="button"
          class="secondary reset-btn"
          @click="workbench.openTool('output')"
        >
          {{ t("settings.openOutputTab") }}
        </button>
        <button
          type="button"
          class="secondary reset-btn"
          @click="workbench.openTool('pdf')"
        >
          {{ t("settings.openPdfTab") }}
        </button>
        <button
          type="button"
          class="secondary reset-btn"
          @click="layout.reset()"
        >
          {{ t("toolbar.resetLayout") }}
        </button>
      </section>

      <section class="settings-section muted-section">
        <h4>{{ t("settings.sectionAbout") }}</h4>
        <p class="hint">{{ t("settings.aboutBody") }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.settings-scroll {
  flex: 1 1 auto;
  overflow: auto;
  padding: 0.5rem 0.75rem 1rem;
}
.settings-section {
  margin-bottom: 1.1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}
.settings-section h4 {
  margin: 0 0 0.55rem;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  font-weight: 600;
}
.settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.85rem;
  margin-bottom: 0.35rem;
}
.settings-row select {
  min-width: 7.5rem;
  background: var(--input-bg, #1e293b);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.25rem 0.4rem;
}
.settings-check {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.85rem;
  margin: 0.35rem 0;
  cursor: pointer;
}
.hint {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: var(--muted);
  line-height: 1.4;
}
.reset-btn {
  margin-top: 0.6rem;
  width: 100%;
}
.muted-section {
  border-bottom: none;
}
</style>
