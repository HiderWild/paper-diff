# paper-diff manual smoke (L0 + hardening)

15–20 minutes. API on `:8000`, web on Vite default.

```bash
cd apps/api && PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP=false uvicorn app.main:app --reload --port 8000
cd apps/web && npm run dev
```

## Checklist

1. Open web UI (zh-CN default).
2. **Import project** — single zip with `main.tex` (+ optional `fig.png`).
3. Tree shows files; open `.tex` → Monaco left filled. Comparer title is **「比较器」** only when empty; with file shows **谁 ↔ 谁**.  
3b. Click **⇄ 对调左右** → sides swap display.  
3c. Click a project **`.pdf`** in the tree → PDF pane shows that file (title `PDF · path`), not only compile artifact.
4. **Add compare zone** (zip or folder); activate → right side shows zone text; tree badges update.
5. Accept a word/sentence chip → left updates; **Undo** restores.
6. Select TeX root → **Compile** (Docker optional; without image expect clear error).
7. **Git** activity: status, commit message, history list.
8. Pick commits A/B → Compare → open a path (preview, Accept disabled) → clear preview.
9. **Zone from commit** on a log row → new zone appears.
10. **Discard** uncommitted after edit (confirm).
11. Open `fig.png` → ImagePreview (work [| zone]).
12. If zone has `.csv`, open it → CSV panel shows changed rows (or empty message).
13. **Agent**: Analyze / Propose / Apply (confirm); provider badge shows `stub`.
14. Agent chat input → reply appears in log.
15. Layout preset select + **⌘⇧P** command palette (Compile / Toggle PDF).
16. Large zip (optional): progress bar visible during upload.
17. Export project zip downloads work tree.
18. Advanced dual-zip still works if needed.

## API-only checks

```bash
cd apps/api && pytest -v --ignore=tests/test_compile_smoke.py
curl -s localhost:8000/api/v1/health
```
