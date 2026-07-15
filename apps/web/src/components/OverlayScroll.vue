<script setup lang="ts">
/**
 * VS Code-like overlay scrollbar: thin semi-transparent thumb floating over content.
 * Does not reserve layout width — appear/disappear never shifts the DOM.
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    /** Extra class on the scrollport */
    contentClass?: string;
    /** Thumb thickness in px */
    thickness?: number;
    /** Hide delay after scroll ends (ms) */
    hideDelayMs?: number;
  }>(),
  {
    contentClass: "",
    thickness: 8,
    hideDelayMs: 900,
  }
);

const viewport = ref<HTMLElement | null>(null);
const track = ref<HTMLElement | null>(null);
const thumbH = ref(0);
const thumbTop = ref(0);
const visible = ref(false);
const hovering = ref(false);
const dragging = ref(false);
const needed = ref(false);

let hideTimer: ReturnType<typeof setTimeout> | null = null;
let dragStartY = 0;
let dragStartScroll = 0;
let ro: ResizeObserver | null = null;

function clearHideTimer() {
  if (hideTimer) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}

function scheduleHide() {
  clearHideTimer();
  if (hovering.value || dragging.value) return;
  hideTimer = setTimeout(() => {
    visible.value = false;
    hideTimer = null;
  }, props.hideDelayMs);
}

function show() {
  visible.value = true;
  scheduleHide();
}

function measure() {
  const el = viewport.value;
  if (!el) return;
  const { clientHeight, scrollHeight, scrollTop } = el;
  const canScroll = scrollHeight > clientHeight + 1;
  needed.value = canScroll;
  if (!canScroll) {
    thumbH.value = 0;
    thumbTop.value = 0;
    return;
  }
  const ratio = clientHeight / scrollHeight;
  const h = Math.max(24, Math.round(clientHeight * ratio));
  const maxTop = clientHeight - h;
  const maxScroll = scrollHeight - clientHeight;
  const top =
    maxScroll <= 0 ? 0 : Math.round((scrollTop / maxScroll) * maxTop);
  thumbH.value = h;
  thumbTop.value = top;
}

function onScroll() {
  measure();
  show();
}

function onViewportEnter() {
  hovering.value = true;
  measure();
  if (needed.value) visible.value = true;
  clearHideTimer();
}

function onViewportLeave() {
  hovering.value = false;
  if (!dragging.value) scheduleHide();
}

function scrollToThumb(clientY: number) {
  const el = viewport.value;
  const tr = track.value;
  if (!el || !tr) return;
  const rect = tr.getBoundingClientRect();
  const y = clientY - rect.top - thumbH.value / 2;
  const maxTop = el.clientHeight - thumbH.value;
  const clamped = Math.max(0, Math.min(maxTop, y));
  const maxScroll = el.scrollHeight - el.clientHeight;
  el.scrollTop = maxTop <= 0 ? 0 : (clamped / maxTop) * maxScroll;
}

function onTrackPointerDown(e: PointerEvent) {
  if ((e.target as HTMLElement).closest?.(".os-thumb")) return;
  e.preventDefault();
  scrollToThumb(e.clientY);
  show();
}

function onThumbPointerDown(e: PointerEvent) {
  e.preventDefault();
  e.stopPropagation();
  const el = viewport.value;
  if (!el) return;
  dragging.value = true;
  dragStartY = e.clientY;
  dragStartScroll = el.scrollTop;
  (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  visible.value = true;
  clearHideTimer();
}

function onThumbPointerMove(e: PointerEvent) {
  if (!dragging.value) return;
  const el = viewport.value;
  if (!el) return;
  const maxTop = el.clientHeight - thumbH.value;
  const maxScroll = el.scrollHeight - el.clientHeight;
  if (maxTop <= 0 || maxScroll <= 0) return;
  const dy = e.clientY - dragStartY;
  el.scrollTop = dragStartScroll + (dy / maxTop) * maxScroll;
}

function onThumbPointerUp(e: PointerEvent) {
  if (!dragging.value) return;
  dragging.value = false;
  try {
    (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
  } catch {
    /* ignore */
  }
  scheduleHide();
}

function bindObserver() {
  const el = viewport.value;
  if (!el || typeof ResizeObserver === "undefined") return;
  ro = new ResizeObserver(() => {
    measure();
  });
  ro.observe(el);
  // also watch first child size changes
  if (el.firstElementChild) ro.observe(el.firstElementChild);
}

onMounted(async () => {
  await nextTick();
  measure();
  bindObserver();
  // remeasure when content mutates frequently (tree expand)
  const el = viewport.value;
  if (el) {
    const mo = new MutationObserver(() => measure());
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    onBeforeUnmount(() => mo.disconnect());
  }
});

onBeforeUnmount(() => {
  clearHideTimer();
  ro?.disconnect();
  ro = null;
});

watch(
  () => props.thickness,
  () => measure()
);

defineExpose({
  scrollEl: viewport,
  remount: () => {
    measure();
  },
});
</script>

<template>
  <div
    class="os-root"
    @pointerenter="onViewportEnter"
    @pointerleave="onViewportLeave"
  >
    <div
      ref="viewport"
      class="os-viewport"
      :class="contentClass"
      @scroll.passive="onScroll"
    >
      <slot />
    </div>
    <div
      v-show="needed"
      ref="track"
      class="os-track"
      :class="{ visible: visible || dragging || hovering }"
      :style="{ width: thickness + 'px' }"
      @pointerdown="onTrackPointerDown"
    >
      <div
        class="os-thumb"
        :class="{ dragging }"
        :style="{
          height: thumbH + 'px',
          transform: `translateY(${thumbTop}px)`,
          width: thickness - 2 + 'px',
        }"
        @pointerdown="onThumbPointerDown"
        @pointermove="onThumbPointerMove"
        @pointerup="onThumbPointerUp"
        @pointercancel="onThumbPointerUp"
      />
    </div>
  </div>
</template>

<style scoped>
.os-root {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.os-viewport {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  /* Never reserve gutter — layout must not jump */
  scrollbar-width: none; /* Firefox */
  scrollbar-gutter: auto;
}
.os-viewport::-webkit-scrollbar {
  width: 0 !important;
  height: 0 !important;
  display: none;
}
.os-track {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 5;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.16s ease;
  /* slight inset so thumb is not flush on edge */
  padding: 2px 1px;
  box-sizing: border-box;
}
.os-track.visible {
  opacity: 1;
  pointer-events: auto;
}
.os-thumb {
  position: absolute;
  top: 0;
  right: 1px;
  border-radius: 999px;
  /* VS Code-like gray translucent thumb */
  background: color-mix(in srgb, var(--muted) 55%, transparent);
  pointer-events: auto;
  cursor: default;
  transition: background 0.12s ease, opacity 0.12s ease;
  will-change: transform;
}
.os-thumb:hover,
.os-thumb.dragging {
  background: color-mix(in srgb, var(--muted) 80%, transparent);
}
</style>
