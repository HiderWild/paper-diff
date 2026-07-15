<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { storeToRefs } from "pinia";
import type { DiffUnit } from "../../features/diff/sentenceMapper";
import { useProjectStore } from "../../stores/project";

const props = defineProps<{
  path: string;
  units: DiffUnit[];
}>();

const emit = defineEmits<{
  acceptUnit: [unit: DiffUnit];
  acceptAll: [];
  afterMutation: [leftContent: string | null];
}>();

const { t } = useI18n();
const store = useProjectStore();
const {
  sidesSwapped,
  activeZoneId,
  zones,
  busy,
  pair,
} = storeToRefs(store);

const unitFilter = computed(() => "sentence" as const);

const visibleUnits = computed(() =>
  props.units.filter((u) => u.granularity === unitFilter.value || true).slice(0, 40)
);

const title = computed(() => {
  const zone =
    zones.value.find((z) => z.id === activeZoneId.value)?.name ||
    t("panels.sideZone");
  const left = sidesSwapped.value ? zone : t("panels.sideProject");
  const right = sidesSwapped.value ? t("panels.sideProject") : zone;
  if (!props.path) return t("panels.comparer");
  return t("panels.diffHeaderWith", { left, right });
});

async function onAccept(u: DiffUnit) {
  const content = await store.doAccept(u);
  emit("acceptUnit", u);
  emit("afterMutation", content ?? null);
}

async function onAcceptAll() {
  if (!pair.value) return;
  if (store.isDirty(props.path)) {
    if (!confirm(t("tools.dirtyAcceptConfirm"))) return;
  }
  const content = await store.doAcceptAll();
  emit("acceptAll");
  emit("afterMutation", content ?? null);
}
</script>

<template>
  <div class="cmp-chrome">
    <div class="cmp-title-row">
      <span class="cmp-title">{{ title }}</span>
      <span class="cmp-path muted">{{ path }}</span>
      <button
        type="button"
        class="mini secondary"
        :class="{ 'active-toggle': sidesSwapped }"
        :title="t('panels.swapSides')"
        :disabled="busy"
        @click="store.toggleSidesSwapped()"
      >
        ⇄ {{ t("panels.swapSides") }}
      </button>
      <button
        type="button"
        class="mini"
        :disabled="busy || !pair"
        @click="onAcceptAll"
      >
        {{ t("toolbar.acceptFile") }}
      </button>
    </div>
    <div v-if="visibleUnits.length" class="unit-bar">
      <button
        v-for="u in visibleUnits"
        :key="u.id"
        type="button"
        class="unit-chip"
        :class="u.granularity"
        :disabled="busy"
        :title="`${u.leftText} → ${u.rightText}`"
        @click="onAccept(u)"
      >
        {{
          t("units.accept", {
            granularity: t(`units.${u.granularity}`),
          })
        }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.cmp-chrome {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--panel-header);
}
.cmp-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.55rem;
  font-size: 0.8rem;
}
.cmp-title {
  font-weight: 600;
}
.cmp-path {
  flex: 1;
  min-width: 4rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.75rem;
}
.unit-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  padding: 0.3rem 0.55rem 0.45rem;
  max-height: 5.5rem;
  overflow: auto;
}
.active-toggle {
  outline: 1px solid var(--accent);
}
.muted {
  color: var(--muted);
}
</style>
