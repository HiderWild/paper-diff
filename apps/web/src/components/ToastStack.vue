<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useWorkspaceStore } from "../stores/workspace";

const ws = useWorkspaceStore();
const { toasts } = storeToRefs(ws);
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="t.level || 'warn'"
      @click="ws.dismissToast(t.id)"
    >
      {{ t.message }}
    </div>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  left: 1rem;
  bottom: 1rem;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-width: min(360px, 90vw);
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  padding: 0.55rem 0.75rem;
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.35;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border);
  cursor: pointer;
  background: #1e293b;
  color: var(--text);
}
.toast.warn {
  background: #422006;
  border-color: #b45309;
  color: #fde68a;
}
.toast.error {
  background: #450a0a;
  border-color: #b91c1c;
  color: #fecaca;
}
.toast.info {
  background: #0c4a6e;
  border-color: #0284c7;
  color: #e0f2fe;
}
</style>
