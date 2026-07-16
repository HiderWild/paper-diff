import { ref, type Ref } from "vue";
import { getTexContext } from "../../shared/api";
import { EMPTY_TEX_CONTEXT, type TexContext } from "./texSentenceContext";

// Module-level cache: Map<projectId, TexContext>
const _cache = new Map<string, TexContext>();
// Module-level in-flight: Map<projectId, Promise<TexContext>>
const _inflight = new Map<string, Promise<TexContext>>();

export function useTexContext(projectId: Ref<string | null>) {
  const ctx = ref<TexContext>(EMPTY_TEX_CONTEXT);

  async function fetchCtx(pid: string): Promise<TexContext> {
    // Check cache first
    if (_cache.has(pid)) return _cache.get(pid)!;
    // Check in-flight
    if (_inflight.has(pid)) return _inflight.get(pid)!;
    // Start fetch
    const p = (async () => {
      try {
        const data = await getTexContext(pid);
        const tc: TexContext = {
          compiled: !!data.compiled,
          citations: data.citations ?? {},
          labels: data.labels ?? {},
          bibliography: data.bibliography ?? undefined,
        };
        _cache.set(pid, tc);
        return tc;
      } catch (e) {
        console.warn("[useTexContext] fetch failed:", e);
        return { ...EMPTY_TEX_CONTEXT };
      } finally {
        _inflight.delete(pid);
      }
    })();
    _inflight.set(pid, p);
    return p;
  }

  async function refresh(): Promise<void> {
    const pid = projectId.value;
    if (!pid) return;
    // Force re-fetch: clear cache for this project
    _cache.delete(pid);
    const tc = await fetchCtx(pid);
    ctx.value = tc;
  }

  async function ensure(): Promise<void> {
    const pid = projectId.value;
    if (!pid) return;
    const tc = await fetchCtx(pid);
    ctx.value = tc;
  }

  // Auto-load on projectId change if not cached — but only when called.
  // Do NOT auto-watch in the composable; let callers call ensure() explicitly.

  return { ctx, refresh, ensure };
}

// Test helper: clear the module-level cache (for vitest)
export function _clearTexContextCache(): void {
  _cache.clear();
  _inflight.clear();
}
