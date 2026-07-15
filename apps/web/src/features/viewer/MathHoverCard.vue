<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import {
  currentThemeMode,
  injectMathHoverCss,
  renderMathHoverHtml,
} from "./renderMathHoverHtml";

const props = defineProps<{
  latex: string;
  display: boolean;
  x: number;
  y: number;
}>();

const emit = defineEmits<{
  dismiss: [];
  pointerEnter: [];
  pointerLeave: [];
}>();

const root = ref<HTMLElement | null>(null);
const theme = ref<"dark" | "light">(currentThemeMode());

const html = computed(() =>
  renderMathHoverHtml(props.latex, props.display, theme.value)
);

function refreshTheme() {
  theme.value = currentThemeMode();
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    emit("dismiss");
  }
}

onMounted(() => {
  injectMathHoverCss();
  refreshTheme();
  window.addEventListener("keydown", onKey, true);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey, true);
});

watch(
  () => [props.latex, props.display] as const,
  () => refreshTheme()
);
</script>

<template>
  <div
    ref="root"
    class="math-hover-float"
    :class="theme"
    :style="{ left: x + 'px', top: y + 'px' }"
    role="tooltip"
    @pointerenter="emit('pointerEnter')"
    @pointerleave="emit('pointerLeave')"
    @pointerdown.stop
    @wheel.stop
  >
    <div class="math-hover-body" v-html="html" />
  </div>
</template>

<style scoped>
.math-hover-float {
  position: fixed;
  z-index: 240;
  transform: translateX(-50%);
  max-width: min(36rem, 92vw);
  pointer-events: auto;
  filter: drop-shadow(0 10px 24px rgba(0, 0, 0, 0.35));
}
.math-hover-body :deep(.pd-math-hover) {
  /* card chrome lives inside renderMathHoverHtml */
}
</style>
