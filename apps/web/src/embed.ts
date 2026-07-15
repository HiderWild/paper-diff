/**
 * Embeddable entry for host apps.
 *
 * ```ts
 * import { mountPaperDiff } from 'paper-diff-web/embed'
 * const api = mountPaperDiff(document.getElementById('root')!, {
 *   apiBase: 'https://api.example.com',
 *   projectId: 'optional-existing',
 *   token: 'optional', // reserved
 * })
 * // api.destroy()
 * ```
 */
import { createApp, type App } from "vue";
import { createPinia } from "pinia";
import AppRoot from "./App.vue";
import i18n, { setLocale, type AppLocale } from "./i18n";
import { setApiBase } from "./shared/api";
import { useProjectStore } from "./stores/project";
import "./styles.css";

export type MountOptions = {
  apiBase?: string;
  projectId?: string;
  /** Reserved for host auth pass-through */
  token?: string;
  autoCompile?: boolean;
  /** UI locale: zh-CN (default) or en */
  locale?: AppLocale;
};

export type PaperDiffHandle = {
  destroy: () => void;
  getProjectId: () => string | null;
};

export function mountPaperDiff(
  el: HTMLElement,
  options: MountOptions = {}
): PaperDiffHandle {
  if (options.apiBase) setApiBase(options.apiBase);

  const pinia = createPinia();
  const app: App = createApp(AppRoot);
  app.use(pinia);
  app.use(i18n);
  if (options.locale) setLocale(options.locale);
  app.mount(el);

  const store = useProjectStore(pinia);
  if (options.projectId) {
    store.setProjectId(options.projectId);
    void store.refreshIndex().then(async () => {
      const first = store.files[0];
      if (first) await store.openFile(first.path);
    });
  }
  if (options.autoCompile != null) store.autoCompile = options.autoCompile;

  return {
    destroy: () => {
      app.unmount();
    },
    getProjectId: () => store.projectId,
  };
}

export default mountPaperDiff;
