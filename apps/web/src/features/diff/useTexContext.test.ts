import { describe, expect, it, vi, beforeEach } from "vitest";
import { ref } from "vue";
import { useTexContext, _clearTexContextCache } from "./useTexContext";
import { EMPTY_TEX_CONTEXT } from "./texSentenceContext";

describe("useTexContext", () => {
  beforeEach(() => {
    _clearTexContextCache();
    vi.restoreAllMocks();
  });

  function mockFetchOk(payload: unknown) {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(payload),
    });
    vi.stubGlobal("fetch", f);
    return f;
  }

  function mockFetchNotOk(status: number) {
    const f = vi.fn().mockResolvedValue({
      ok: false,
      status,
      statusText: "Not Found",
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({ error: { message: "nope" } }),
    });
    vi.stubGlobal("fetch", f);
    return f;
  }

  it("fetches and caches context on ensure", async () => {
    const f = mockFetchOk({
      compiled: true,
      citations: { a: "1" },
      labels: {},
      bibliography: null,
    });
    const { ctx, ensure } = useTexContext(ref("pid"));
    await ensure();
    expect(ctx.value.compiled).toBe(true);
    expect(ctx.value.citations.a).toBe("1");
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("second ensure does not re-fetch (cache hit)", async () => {
    const f = mockFetchOk({
      compiled: true,
      citations: { a: "1" },
      labels: {},
    });
    const { ensure } = useTexContext(ref("pid"));
    await ensure();
    await ensure();
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("refresh clears cache and re-fetches", async () => {
    const f = mockFetchOk({
      compiled: true,
      citations: { a: "1" },
      labels: {},
    });
    const { ctx, ensure, refresh } = useTexContext(ref("pid"));
    await ensure();
    expect(f).toHaveBeenCalledTimes(1);
    await refresh();
    expect(f).toHaveBeenCalledTimes(2);
    expect(ctx.value.compiled).toBe(true);
  });

  it("failed fetch returns empty context", async () => {
    const f = vi.fn().mockRejectedValue(new Error("network"));
    vi.stubGlobal("fetch", f);
    const { ctx, ensure } = useTexContext(ref("pid"));
    await ensure();
    expect(ctx.value).toEqual(EMPTY_TEX_CONTEXT);
    expect(ctx.value.compiled).toBe(false);
  });

  it("failed fetch (non-ok status) returns empty", async () => {
    const f = mockFetchNotOk(404);
    const { ctx, ensure } = useTexContext(ref("pid"));
    await ensure();
    expect(ctx.value).toEqual(EMPTY_TEX_CONTEXT);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("null projectId does not fetch", async () => {
    const f = mockFetchOk({ compiled: true, citations: {}, labels: {} });
    const { ensure } = useTexContext(ref(null));
    await ensure();
    expect(f).not.toHaveBeenCalled();
  });

  it("inflight dedup: concurrent ensure calls fetch once", async () => {
    const f = mockFetchOk({
      compiled: true,
      citations: { a: "1" },
      labels: {},
    });
    const { ensure } = useTexContext(ref("pid"));
    const p1 = ensure();
    const p2 = ensure();
    await Promise.all([p1, p2]);
    expect(f).toHaveBeenCalledTimes(1);
  });
});
