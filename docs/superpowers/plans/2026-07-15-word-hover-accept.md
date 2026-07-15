# Word / phrase hover-accept plan

**Status:** Phase 1–4 MVP landed (hover card + decorations + pullUnit; S-tier)  
**Product:** paper-diff text comparer (Monaco Diff only)  
**Related:** `MonacoDiff.vue`, `sentenceMapper.ts`, `applySnippet.ts`, project store accept/undo, large-file tiers  

## Goal

When Monaco marks a **brighter inline** change (true word/phrase-level divergence), hovering that span opens a **floating card** showing work vs compare text and a **local replace** button (pull compare → work). The op must be **undoable** via the existing accept/undo stack.

**Non-goals (this plan):**

- Forking / patching Monaco source  
- PDF / image / docx hover accept  
- Server-side re-alignment beyond current accept APIs  
- Replacing gutter arrows (they stay for line/block/hunk)

## Ground truth (already in tree)

| Piece | Location | Ready? |
|-------|----------|--------|
| Line + char diffs from Monaco | `editor.getLineChanges()` → optional `charChanges` | Yes |
| Word / sentence / hunk units | `buildDiffUnits` in `sentenceMapper.ts` | Yes |
| Apply unit to work buffer | `applyUnitToWorkText` / `applyCompareUnit` / `doAccept` | Yes |
| Undo | `doUndo` + backend accept snapshots | Yes |
| Pull wiring | `MonacoDiff` `@pull-unit` → `ToolBody.onPullUnit` | Yes (gutter) |
| Hover card + hit-test on word ranges | — | **No** |
| Decorations binding tip hit area to units | — | **No** |

**Semantics (locked):**

- Data sides: **left = work (editable)**, **right = compare target (zone/git/revised)**  
- UI may `sidesSwapped`; card labels always true-source (“工作区 / 对照”), never “左/右”  
- Replace = same as arrow: **compare → work** for that unit only  
- **L / M tiers:** `wordUnits: false` today — hover-accept only when word units exist (mainly **S**, optionally widen later)

---

## Architecture (target)

```
Monaco DiffEditor
  onDidUpdateDiff
    → getLineChanges()
    → buildDiffUnits(..., { wordUnits })
    → lastUnits[]
    → syncWordDecorations(word units)   [Phase 2]
    → placeArrows(hunk/line/block)      [existing]

Mouse on original/modified editor
  → hitTestWordUnit(units, side, line, col)   [Phase 1 pure]
  → debounce show WordHoverCard               [Phase 2]
       leftText / rightText
       [采纳此处] → emit pullUnit(unit)       [existing pipeline]
```

**Do not** scrape Monaco’s painted red pixels. Tip region = **our** unit ranges (optionally mirrored with decorations).

---

## Phase 0 — Spec freeze & fixtures (½ day)

**Deliverables**

- [x] This plan document  
- [ ] Short product acceptance criteria (checklist below) agreed  
- [ ] 3–5 golden fixtures: single token change, multi-token same line, insert-only, delete-only, LaTeX command token  

**Acceptance criteria (Phase A product)**

1. On a small file with `The analysis` vs different phrase: bright inline + hover card after ~350ms.  
2. Card shows both sides’ strings and one primary button.  
3. Click apply updates work buffer only for that span; other text unchanged.  
4. Toolbar undo restores pre-apply content.  
5. No card on L-tier files (or only if we later enable word units).  
6. With sides swapped, button still pulls **compare → work**.  

**Exit:** fixtures checked into `apps/web/src/features/diff/fixtures/` or as unit-test strings.

---

## Phase 1 — Pure hit-test + unit indexing (1 day)

**Goal:** No UI yet; solid functions + tests.

**New module (suggested):**  
`apps/web/src/features/diff/wordHover.ts`

| Function | Behavior |
|----------|----------|
| `wordUnitsOf(units)` | Filter `granularity === "word"` |
| `rangeContains(r, line, col0)` | 0-based cols; inclusive/exclusive rules documented |
| `hitTestWordUnit(units, side, line, col0)` | Prefer **smallest** containing range; side is `"work"` \| `"compare"` mapping to left/right |
| `unitCardModel(unit)` | `{ workText, compareText, unit }` for the card |

**Tests:** `wordHover.test.ts` — empty, insert, delete, nested preference, off-range null.

**Exit:** tests green; no product UI change.

---

## Phase 2 — Decorations + hover card shell (2–3 days)

**Goal:** Visible hover UX; apply can still be stubbed then wired.

### 2a Monaco decorations

In `MonacoDiff.vue` when `!singlePane && showGutterActions` (or a new prop `enableWordHover`):

- After units recompute, map each word unit to decorations on:
  - **work** editor model = original (true left)  
  - **compare** editor model = modified (true right)  
- If `sidesSwapped`, swap which editor shows which decoration set (data still left=work).  
- Style: subtle underline / outline so tip hit area matches “clickable phrase” (can be near-invisible if Monaco char highlight is enough; still need stable ranges).  
- Clear decorations on unmount / path change / single-pane.

### 2b Hover controller

- Debounce mouse move ~300–400ms.  
- Resolve mouse target → line/col (Monaco mouse target API).  
- `hitTestWordUnit` → set `hover = { unit, x, y, editor }`.  
- Hide on leave editor, scroll, unit recompute, Escape, successful apply.

### 2c Floating card component

**Suggested:** `apps/web/src/features/diff/WordHoverCard.vue`  
Teleported or absolutely positioned over `diff-wrap`.

Content:

- Work: monospace snippet (truncate ~120 chars with expand)  
- Compare: monospace snippet  
- Primary: `采纳此处` / “Apply here”  
- Optional secondary: dismiss  

**i18n:** `hoverAccept.*` keys in zh-CN + en.

### 2d Wire apply

Card button → existing `emit('pullUnit', unit)` → no new store API.

**Exit:** manual smoke on fixture files; unit tests for hit-test; typecheck green.

---

## Phase 3 — Apply reliability & undo UX (1–2 days)

**Goal:** Trustable mutations.

- [ ] Verify `applyUnitToWorkText` for pure insert/delete word units (add tests if gaps).  
- [ ] After apply: remount/units refresh (existing `targetTick` / buffer sync path).  
- [ ] Dirty + autosave interaction: applied content marks dirty / saves like other accepts.  
- [ ] Undo: single click restores; optional toast “已采纳词级修改 · 可撤销”.  
- [ ] If client apply fails, surface error; do not leave half decoration state.

**Exit:** automated tests for insert/delete/replace word units + one store-level mock apply.

---

## Phase 4 — Side-swap, tiers, performance (1–2 days)

| Topic | Work |
|-------|------|
| `sidesSwapped` | Hit-test maps visual editor → work/compare; card labels fixed |
| Tier S | Full word hover on |
| Tier M | Optional: enable `wordUnits: true` only for visible hunks **or** keep off and document “small files only” for v1 |
| Tier L | No word hover (keep `wordUnits: false`) |
| Perf | Cap decorations (e.g. max 500 word units); viewport-only optional later |
| Scroll/zoom | Hide card on scroll of either editor |

**Exit:** matrix checklist for S/M/L × swapped × not swapped.

---

## Phase 5 — Polish (optional, 1–2 days)

- Sentence-level hover (parent of words) with “采纳整句”  
- Keyboard: Enter apply when card focused  
- Replace remaining native `title=` tips with shared float-tip style (separate from word card)  
- Telemetry-free a11y: `role="dialog"` / aria-label on card  
- Visual alignment: decoration color tokens vs Monaco theme  

---

## Implementation order (execution slices)

Do in this order when coding starts:

1. Phase 1 pure module + tests  
2. Phase 2 decorations + card UI (apply wired)  
3. Phase 3 apply/undo hardening  
4. Phase 4 swap + tier policy  
5. Phase 5 only if needed  

Prefer **vertical slices** after Phase 1: each PR should leave main usable (feature-flag if needed).

### Suggested feature flag

`settings` or prop: `wordHoverAccept: boolean` default `true` for S-tier only. Easy kill switch.

---

## Files likely touched

| File | Role |
|------|------|
| `apps/web/src/features/diff/wordHover.ts` | NEW pure hit-test |
| `apps/web/src/features/diff/wordHover.test.ts` | NEW tests |
| `apps/web/src/features/diff/WordHoverCard.vue` | NEW UI |
| `apps/web/src/features/diff/MonacoDiff.vue` | decorations, mouse, card host |
| `apps/web/src/components/workbench/ToolBody.vue` | maybe pass props / already has pullUnit |
| `apps/web/src/i18n/locales/zh-CN.ts`, `en.ts` | strings |
| `apps/web/src/features/diff/applySnippet.test.ts` | word edge cases |
| `apps/web/src/features/diff/largeFileTier.ts` | only if M-tier policy changes |

**Out of scope files:** PdfPane, ImagePreview, zone explorer, AGPL LICENSE (no Monaco fork).

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `charChanges` empty sometimes | Existing tokenize fallback; card still uses unit ranges |
| Hover fights gutter arrows | Card offset; higher z-index only over text; arrows keep own hit area |
| Stale ranges after edit | Recompute units + decorations on content change |
| Over-decoration cost | Cap count; S-tier only at first |
| User expects L files too | Document tier policy; optional Phase 4 viewport words |

---

## Definition of done (whole feature)

- Phase 1–3 complete; Phase 4 matrix signed off  
- `npm test` + `vue-tsc -b` green  
- Manual smoke: swap on/off, undo, S-file multi-word line  
- AGENTS.md one-liner: word hover accept location + tier limits  
- No Monaco fork  

---

## Continuity notes for implementers

- Prefer **true-source** left/right always; display swap is visual only.  
- Reuse `pullUnit` — do not invent a second accept path.  
- Column coords: DiffUnit stores **0-based** cols; Monaco API often **1-based** — convert at boundary only.  
- After accept remount, hover state must clear.  

---

## Status log

| Date | Note |
|------|------|
| 2026-07-15 | Plan authored after Monaco API / architecture Q&A; implementation not started. |
| 2026-07-15 | Implemented: `wordHover.ts` + tests, `WordHoverCard.vue`, decorations + mouse hover in `MonacoDiff`, `sidesSwapped` + S-tier via `tierOpts.wordUnits`, i18n. Phase 5 polish deferred. |
