<script setup lang="ts">
/**
 * Pick a file at a git commit for the comparer compare-side.
 * Content is loaded later via git show (no on-disk checkout for the picker).
 */
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import OverlayScroll from "../../components/OverlayScroll.vue";
import FileTree from "../tree/FileTree.vue";
import type { FileMeta } from "../tree/buildTree";
import {
  gitLog,
  gitLsTree,
  type GitCommit,
} from "../../shared/api";

const props = defineProps<{
  open: boolean;
  projectId: string | null;
  /** Prefer this work path when selecting matching file in tree */
  preferredPath?: string | null;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [payload: { ref: string; path: string; short?: string }];
}>();

const { t } = useI18n();
const commits = ref<GitCommit[]>([]);
const selectedRef = ref("");
const selectedPath = ref<string | null>(null);
const treeFiles = ref<FileMeta[]>([]);
const loadingLog = ref(false);
const loadingTree = ref(false);
const error = ref("");
const showDot = ref(false);
const filter = ref("");

const shortSelected = computed(() => {
  const c = commits.value.find(
    (x) => x.sha === selectedRef.value || x.short === selectedRef.value
  );
  return (c?.short || selectedRef.value || "").slice(0, 10);
});

const filteredCommits = computed(() => {
  const q = filter.value.trim().toLowerCase();
  if (!q) return commits.value;
  return commits.value.filter((c) => {
    const blob = `${c.sha} ${c.short} ${c.subject} ${c.author || ""}`.toLowerCase();
    return blob.includes(q);
  });
});

const canConfirm = computed(
  () => !!(selectedRef.value && selectedPath.value)
);

async function loadLog() {
  if (!props.projectId) return;
  loadingLog.value = true;
  error.value = "";
  try {
    const res = await gitLog(props.projectId, 80);
    commits.value = res.commits || [];
    if (!selectedRef.value && commits.value[0]) {
      selectedRef.value = commits.value[0].sha || commits.value[0].short;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    commits.value = [];
  } finally {
    loadingLog.value = false;
  }
}

async function loadTree(ref: string) {
  if (!props.projectId || !ref) {
    treeFiles.value = [];
    return;
  }
  loadingTree.value = true;
  error.value = "";
  selectedPath.value = null;
  try {
    const res = await gitLsTree(props.projectId, ref, { recursive: true });
    treeFiles.value = (res.files || []).map((f) => ({
      path: f.path,
      status: "unknown",
      kind: f.kind || "text",
      is_dot: f.path.split("/").some((p) => p.startsWith(".")),
    }));
    // Prefer same path as work if present
    if (
      props.preferredPath &&
      treeFiles.value.some((f) => f.path === props.preferredPath)
    ) {
      selectedPath.value = props.preferredPath;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    treeFiles.value = [];
  } finally {
    loadingTree.value = false;
  }
}

function pickCommit(c: GitCommit) {
  selectedRef.value = c.sha || c.short;
  void loadTree(selectedRef.value);
}

function onOpenFile(path: string) {
  selectedPath.value = path;
}

function confirm() {
  if (!canConfirm.value || !selectedPath.value) return;
  emit("confirm", {
    ref: selectedRef.value,
    path: selectedPath.value,
    short: shortSelected.value,
  });
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      filter.value = "";
      selectedPath.value = null;
      void loadLog().then(() => {
        if (selectedRef.value) void loadTree(selectedRef.value);
      });
    }
  }
);
</script>

<template>
  <div v-if="open" class="modal-overlay" @click.self="emit('close')">
    <div class="modal" role="dialog" :aria-label="t('gitPick.title')">
      <header class="modal-head">
        <h3>{{ t("gitPick.title") }}</h3>
        <button type="button" class="secondary mini" @click="emit('close')">
          {{ t("importModal.cancel") }}
        </button>
      </header>
      <p class="muted hint">{{ t("gitPick.hint") }}</p>
      <p v-if="error" class="error">{{ error }}</p>

      <div class="pick-body">
        <section class="commits-col">
          <div class="col-head">
            <span>{{ t("gitPick.commits") }}</span>
            <input
              v-model="filter"
              type="search"
              class="filter"
              :placeholder="t('gitPick.filterCommits')"
            />
          </div>
          <OverlayScroll content-class="commit-scroll">
            <p v-if="loadingLog" class="muted tiny">{{ t("preview.loading") }}</p>
            <p v-else-if="!filteredCommits.length" class="muted tiny">
              {{ t("gitPick.noCommits") }}
            </p>
            <button
              v-for="c in filteredCommits"
              :key="c.sha || c.short"
              type="button"
              class="commit-row"
              :class="{
                active: selectedRef === c.sha || selectedRef === c.short,
              }"
              @click="pickCommit(c)"
            >
              <span class="sha">{{ (c.short || c.sha || "").slice(0, 10) }}</span>
              <span class="subject">{{ c.subject }}</span>
              <span class="meta muted">{{ c.author }} · {{ c.date }}</span>
            </button>
          </OverlayScroll>
        </section>

        <section class="tree-col">
          <div class="col-head">
            <span>
              {{ t("gitPick.treeAt", { ref: shortSelected || "—" }) }}
            </span>
            <label class="dot">
              <input v-model="showDot" type="checkbox" />
              {{ t("tree.showDotShort") }}
            </label>
          </div>
          <div class="tree-host">
            <p v-if="loadingTree" class="muted tiny">{{ t("preview.loading") }}</p>
            <FileTree
              v-else
              :files="treeFiles"
              :current-path="selectedPath"
              :show-dot-files="showDot"
              :hide-toolbar="true"
              compact
              file-source="work"
              @open="onOpenFile"
              @update:show-dot-files="showDot = $event"
            />
          </div>
          <p v-if="selectedPath" class="selected muted">
            {{ t("gitPick.selected", { path: selectedPath }) }}
          </p>
        </section>
      </div>

      <footer class="modal-foot">
        <button type="button" class="secondary" @click="emit('close')">
          {{ t("importModal.cancel") }}
        </button>
        <button type="button" :disabled="!canConfirm" @click="confirm">
          {{ t("gitPick.confirm") }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}
.modal {
  width: min(960px, 96vw);
  height: min(640px, 90vh);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 0.85rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-head h3 {
  margin: 0;
  font-size: 1rem;
}
.hint {
  margin: 0.4rem 0.85rem 0;
  font-size: 0.8rem;
}
.error {
  color: var(--danger);
  margin: 0.35rem 0.85rem 0;
  font-size: 0.8rem;
}
.pick-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(220px, 34%) 1fr;
  gap: 0;
  border-top: 1px solid var(--border);
  margin-top: 0.5rem;
}
.commits-col,
.tree-col {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
}
.tree-col {
  border-right: none;
}
.col-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.55rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.col-head .filter {
  margin-left: auto;
  flex: 1;
  max-width: 10rem;
  background: var(--input-bg);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 4px;
  padding: 0.15rem 0.35rem;
  font-size: 0.75rem;
}
.col-head .dot {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-weight: 400;
  cursor: pointer;
}
.commits-col :deep(.os-root) {
  flex: 1;
  min-height: 0;
}
:deep(.commit-scroll) {
  padding: 0.25rem;
}
.commit-row {
  display: grid;
  grid-template-columns: 4.5rem 1fr;
  grid-template-rows: auto auto;
  column-gap: 0.4rem;
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  border: none;
  border-radius: 6px;
  padding: 0.35rem 0.45rem;
  margin-bottom: 0.15rem;
  cursor: pointer;
  font-size: 0.78rem;
}
.commit-row:hover {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.commit-row.active {
  background: color-mix(in srgb, var(--accent) 28%, transparent);
}
.sha {
  grid-row: 1 / 3;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  color: var(--accent);
  font-weight: 600;
  align-self: center;
}
.subject {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  font-size: 0.68rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-host {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.tree-host :deep(.file-tree) {
  height: 100%;
}
.tree-host :deep(.os-root) {
  max-height: none;
  height: 100%;
}
.selected {
  flex-shrink: 0;
  padding: 0.35rem 0.55rem;
  border-top: 1px solid var(--border);
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.6rem 0.85rem;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.tiny {
  padding: 0.5rem;
  font-size: 0.8rem;
}
</style>
