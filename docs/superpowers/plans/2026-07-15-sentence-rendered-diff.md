# paper-diff 计划：句级差异渲染预览（路径 C：aux/bbl 映射 + 客户端 KaTeX 渲染）

> **Status:** Draft — 2026-07-15
> **Origin:** 用户提出「句级差异直接展示两个句子 TeX 渲染出来的样子（含 inline 公式、引用、脚注、链接），引用标号要正确」
> **Does not supersede:** `2026-07-15-comparer-preview-hardening.md`（比较器真源 / 箭头 / Word 缩放）
> **Related:**
> - 句级 mapper：`apps/web/src/features/diff/sentenceMapper.ts`
> - 词级 hover：`apps/web/src/features/diff/WordHoverCard.vue`、`wordHover.ts`
> - KaTeX 集成：`apps/web/src/features/viewer/renderMathHoverHtml.ts`、`sanitizeMathLatex.ts`
> - 编译服务：`apps/api/app/services/compile_service.py`（latexmk / latexdiff）
> - 编译产物：`artifacts/{job}.pdf`、`jobs/{job}.log`（**当前未持久化 `.aux` / `.bbl`**）

---

## 0. 一句话

**句级差异 hover 不再只贴 raw text，而是把两侧句子渲染成「TeX 排版后的样子」——inline 公式用 KaTeX、`\cite` 显示为真实编号 `[N]`、`\ref` 显示为 label 编号、`\footnote` 上标 + 句末小字、`\href` 可点链接、`\textbf/\emph` 等正文命令就地排版。引用号正确性由服务端编译时持久化的 `.aux` / `.bbl` 提供 ground truth；未编译过的项目回退到「源码 + 渲染（引用号未结算）」双视图。**

### 0.1 禁止的声称（完成前）

在 **Step 4 DoD** 勾选前，文档与对外说明**不得**写：

- 「句级差异已渲染为最终排版样式」
- 「引用号与 PDF 完全一致」

仅可写：「句级差异支持 TeX 渲染预览；引用号在已编译项目下与 PDF 一致，未编译时显示 `[key]` 占位」。

---

## 1. 现状与缺口（证据）

| ID | 现状 | 缺口 | 证据 |
|----|------|------|------|
| **S1** | KaTeX 已集成，仅渲染**纯数学片段** | 不处理正文 / 引用 / 脚注 / 链接 | `renderMathHoverHtml.ts` 输入是单个 math 表达式 |
| **S2** | 句级 DiffUnit 已扩到完整句子 | hover 仍只贴 raw text 两侧对照 | `WordHoverCard.vue` replace 模板 `<code class="snip">` |
| **S3** | compile 跑 latexmk 生成 `.aux` / `.bbl` | **未持久化**，docker work dir 随用随删 | `compile_service.py` `_store_pdf` 只拷 PDF |
| **S4** | 服务端无 `.aux` 解析 | 无 `citations` / `labels` 映射 API | grep `bibcite\|newlabel` 仅命中 `media.py` 扩展名 |
| **S5** | 客户端无 TeX 正文渲染器 | 无 tokenizer / 无 HTML sanitizer / 无 context 拉取 | grep `renderTexSentence` 无命中 |
| **S6** | 渲染后无法高亮实际改动词 | 词级 DiffUnit 是纯文本切片，渲染后是 HTML | 需要在渲染 HTML 里反向 mark |

---

## 2. 产品决策（强制口径，实施前锁定）

### 2.1 引用号正确性来源

```
ground truth = .aux 文件中的 \bibcite{key}{N} 与 \newlabel{key}{{N}{...}{...}}
```

- **不**用客户端启发式估算（首次出现序）——biblatex / natbib / thebibliography 风格会打穿
- **不**用 `.bbl` 解析 bibliography 条目文本（R0 只取编号；tooltip 留 R2）
- 未编译过的项目：`ctx.compiled === false`，渲染时 `\cite{key}` → `[key]` 占位 + 顶部提示条

### 2.2 渲染范围

| 元素 | 渲染 | 说明 |
|------|------|------|
| inline math `$...$` / `\(...\)` | KaTeX inline | 复用 `sanitizeMathLatex` |
| display math `$$...$$` / `\[...\]` | KaTeX display | 句内仍 inline 排，不强制居中 |
| `\cite{a,b}` / `\citep{}` / `\citet{}` | `[N]` / `[N,M]` | 用 `ctx.citations[key]`；缺省 `[key]` |
| `\ref{key}` / `\eqref{key}` | `N` / `(N)` | 用 `ctx.labels[key]`；缺省 `key` |
| `\autoref{key}` | `<prefix> N` | prefix 由 `\autorefname` 决定，R0 用 `§` 占位 |
| `\footnote{text}` | 上标数字 + 句末小字 | 句内自增计数；跨句不保证 |
| `\href{url}{text}` | `<a target=_blank rel=noopener>` | **只允许 http/https**，否则原样显示 |
| `\url{url}` | `<a>` 显示 url 本身 | 同上 |
| `\textbf{x}` / `\emph{x}` / `\textit{x}` / `\texttt{x}` / `\underline{x}` | `<strong>` / `<em>` / `<i>` / `<code>` / `<u>` | 嵌套支持 |
| `\\` / `\par` | `<br>` / 段落分隔 | 句内通常不出现 |
| 未知 `\\xxx{...}` | mono span 原样显示 | 不崩，不吞参数 |
| 纯文本 | escapeHtml 后直出 | CJK / 英文混排 |

### 2.3 渲染后高亮改动词

- 词级 DiffUnit 的 `leftText` / `rightText` 是**纯文本切片**
- 渲染后是 HTML，无法直接 substring match
- **策略**：渲染时对**非数学 token**保留 `data-pd-raw` 属性存原始文本；高亮阶段在 DOM text node 里做 substring match 包 `<mark class="pd-diff-changed">`
- 数学 token 整体当作一个原子，不内部高亮（避免破坏 KaTeX DOM）

### 2.4 UI 形态

```
┌─────────────────────────────────────────────────┐
│ [替换] 句级差异  [源码 | 渲染]  +  [采用此改动]  │
├─────────────────────────────────────────────────┤
│ work:    We introduce **conformal maps** f:z↦az+b │
│          as in [7].                              │
│          ←                                       │
│ compare: We study **conformal maps** f:z↦az+b    │
│          as in [7].                              │
└─────────────────────────────────────────────────┘
```

- 默认「渲染」视图；toggle 切回「源码」（现有 raw text 模式）
- 未编译时顶部黄条：「引用号未结算，可能不准；编译后显示真实编号」
- 改动词在渲染文本里 `<mark>` 标黄（仅非数学部分）
- 卡片宽度 / 上下翻转沿用现有 `placeFloatFromAnchor` + `estimateHoverCardHeight`

### 2.5 性能预算

- `/tex-context` 首次拉取 ≤ 100ms（`.aux` 通常 < 50KB）
- 客户端缓存 per-project，session 内不重复拉
- 单句渲染 ≤ 20ms（KaTeX 已实测 ~5ms / 表达式）
- hover 打开延迟沿用现有 300ms（sentence）

### 2.6 不做（明确延期）

- ❌ bibliography tooltip（hover `[7]` 显示完整文献条目）→ R2
- ❌ `\autoref` 真实 prefix（`Figure` / `Section` / `Table`）→ R2，需解析 `\autorefname`
- ❌ 跨句 `\footnotemark` / `\footnotetext` 配对 → R2
- ❌ 自定义命令展开（`\newcommand`）→ R2，需客户端 mini preprocessor
- ❌ 段级渲染（用户已明确不需要段级差异）

---

## 3. 实施步骤（按序）

每步结束：相关 vitest +（触及 API 时）pytest + `vue-tsc -b` 绿；本文件勾选。

### Step 0 — 基线与探查（≤2h）

- [ ] 手工确认：现有项目编译一次，检查 docker work dir 里 `.aux` / `.bbl` 是否生成、文件名规则（`{stem}.aux` / `{stem}.bbl`）
- [ ] 记录 `manual-smoke.md` 小节「Sentence rendered diff」：当前句级 hover 是 raw text 截图
- [ ] 冻结：`.aux` 解析正则、`TexContext` DTO 形状
- [ ] Status → `In progress · Step 0`

**G/W/T：** When 打开已编译项目的句级 hover，Then 看到 raw text 两侧对照（证明 S2）。

---

### Step 1 — 服务端持久化 `.aux` / `.bbl`（S3）〔P0〕

**目标：** compile 成功后 `.aux` / `.bbl` 落到 `artifacts/`，可经路由下载。

1. [ ] `compile_service._store_pdf` 旁加 `_store_aux_bbl(ws, job, work_dir, stem)`：
   - 拷 `work_dir/{stem}.aux` → `artifacts/{job}.aux` + `artifacts/latest.aux`
   - 拷 `work_dir/{stem}.bbl` → `artifacts/{job}.bbl` + `artifacts/latest.bbl`（若存在）
   - 失败（文件不存在）静默跳过，不阻断 compile 成功
2. [ ] latexmk 路径调用 `_store_aux_bbl`（`compile_service.py` ~L248）
3. [ ] latexdiff 路径同样调用（`compile_service.py` ~L336，diff.tex 的 `.aux`）
4. [ ] 新增路由 `GET /projects/{id}/artifacts/aux` → 返回 `latest.aux` 文本（`text/plain`）
5. [ ] 新增路由 `GET /projects/{id}/artifacts/bbl` → 返回 `latest.bbl` 文本
6. [ ] 测试：`apps/api/tests/test_compile_aux.py`
   - mock compile 成功 → `artifacts/latest.aux` 存在
   - `.aux` 不存在 → 路由 404 且 compile 仍成功
   - `.bbl` 不存在 → 路由 404 且 compile 仍成功

**G/W/T：** Given 已编译项目，When `GET /artifacts/aux`，Then 返回非空 `.aux` 文本且含 `\bibcite` 或 `\newlabel`。

**回滚：** feature flag `PAPER_DIFF_STORE_AUX=true` 默认真；关则不拷（compile 行为不变）。

---

### Step 2 — 服务端 `tex_context` 解析与路由（S4）〔P0〕

**目标：** `GET /projects/{id}/artifacts/tex-context` 返回结构化映射。

1. [ ] 新增 `apps/api/app/domain/tex_context.py`：
   - `parse_aux(aux_text: str) -> AuxContext`
     - `\bibcite{key}{N}` → `citations: dict[str, str]`（N 可能是数字或字符串如 `lee2023`）
     - `\newlabel{key}{{N}{page}{...}}` → `labels: dict[str, LabelInfo]`（N + page）
     - `\abx@aux@cite{key}{N}`（biblatex）→ 同 `citations`
     - `\abx@aux@number{key}{N}` → 同 `citations`
     - 容错：正则不匹配的行跳过
   - `parse_bbl(bbl_text: str) -> dict[str, str]`（R0 仅抽 `\bibitem{key}` → 粗文本，可选）
   - `build_tex_context(aux: str, bbl: str | None) -> TexContext`
2. [ ] DTO：`app/schemas/dto.py` 加 `TexContextResponse`（`compiled: bool`, `citations`, `labels`, `bibliography?`）
3. [ ] 路由 `GET /projects/{id}/artifacts/tex-context`：
   - 读 `artifacts/latest.aux`；不存在 → `{compiled: false, citations: {}, labels: {}}`
   - 读 `artifacts/latest.bbl`（可选）
   - 返回 `TexContextResponse`
4. [ ] 测试：`apps/api/tests/test_tex_context.py`
   - 标准 `.aux` 含 `\bibcite{lee2023}{7}` → `citations["lee2023"] == "7"`
   - `\newlabel{sec:intro}{{1}{1}}` → `labels["sec:intro"].number == "1"`
   - biblatex `\abx@aux@cite{key}{N}` 解析
   - 空 `.aux` → `compiled: true` 但映射空
   - `.aux` 不存在 → `compiled: false`

**G/W/T：** Given `.aux` 含 `\bibcite{lee2023}{7}`，When `GET /tex-context`，Then `citations.lee2023 == "7"`。

---

### Step 3 — 客户端 TeX 句子渲染器（S5）〔P0〕

**目标：** 纯函数 `renderTexSentence(sentence, ctx) -> SafeHtml`，可单测。

1. [ ] 新增 `apps/web/src/features/diff/texSentenceContext.ts`：
   - `type TexContext = { compiled: boolean; citations: Record<string,string>; labels: Record<string,{number:string;page?:string}> }`
   - `EMPTY_TEX_CONTEXT = { compiled: false, citations: {}, labels: {} }`
2. [ ] 新增 `apps/web/src/features/diff/renderTexSentence.ts`：
   - `renderTexSentence(sentence: string, ctx: TexContext): { html: string; footnoteCount: number }`
   - tokenizer（顺序敏感）：
     1. display math `$$...$$` / `\[...\]` → KaTeX display
     2. inline math `$...$` / `\(...\)` → KaTeX inline
     3. `\cite{...}` / `\citep{...}` / `\citet{...}` / `\citeauthor{...}` → `[N]` / `[N,M]`
     4. `\ref{...}` / `\eqref{...}` / `\autoref{...}` → `N` / `(N)` / `§ N`
     5. `\footnote{...}` → 上标 + 句末小字（递归渲染内部）
     6. `\href{url}{text}` / `\url{url}` → `<a>`（http/https only）
     7. `\textbf{...}` / `\emph{...}` / `\textit{...}` / `\texttt{...}` / `\underline{...}` → HTML 标签（递归）
     8. `\\` / `\par` → `<br>`
     9. 未知 `\\xxx` → `<span class="pd-tex-unknown">\\xxx</span>`
     10. 纯文本 → escapeHtml
   - 输出 sanitized HTML（XSS-safe）
   - 非数学 token 包 `data-pd-raw="<原始文本>"` 供高亮用
3. [ ] 新增 `apps/web/src/features/diff/renderTexSentence.test.ts`：
   - inline math 渲染含 `katex` class
   - `\cite{lee2023}` + ctx → `[7]`
   - `\cite{missing}` + ctx → `[missing]`
   - `\ref{sec:intro}` + ctx → `1`
   - `\href{http://x.com}{text}` → `<a href="http://x.com" target="_blank" rel="noopener">text</a>`
   - `\href{javascript:alert(1)}{x}` → 原样显示（不渲染为 a）
   - `\textbf{bold \emph{italic}}` 嵌套 → `<strong>bold <em>italic</em></strong>`
   - 未知 `\foo{bar}` → mono span 不崩
   - 纯 CJK 文本 escape 正确
   - `data-pd-raw` 在非数学 token 上存在

**G/W/T：** Given `We \textbf{see} $x^2$ as in \cite{lee2023}.` + ctx, When render, Then HTML 含 `<strong>see</strong>`, KaTeX, `[7]`.

---

### Step 4 — 客户端 context 拉取与缓存（S5）〔P0〕

**目标：** composable 按 project 拉一次 `/tex-context` 并缓存。

1. [ ] 新增 `apps/web/src/features/diff/useTexContext.ts`：
   - `useTexContext(projectId: Ref<string>) -> { ctx: Ref<TexContext>; refresh: () => Promise<void> }`
   - 首次访问拉 `/api/v1/projects/{id}/artifacts/tex-context`
   - session 内缓存（Map<projectId, TexContext>）
   - compile 成功后调 `refresh()` 刷新
   - 失败 → `EMPTY_TEX_CONTEXT` + console warn（不阻断 hover）
2. [ ] 在 `project.ts` compile 成功回调里触发 `useTexContext.refresh()`（或事件总线）
3. [ ] 测试：mock fetch → 返回 ctx；二次访问不重复 fetch

**G/W/T：** Given 已编译项目，When 打开句级 hover，Then `useTexContext` 已缓存非空 ctx。

---

### Step 5 — 渲染后高亮改动词（S6）〔P1〕

**目标：** 渲染 HTML 里实际改动的词被 `<mark>` 标黄。

1. [ ] 新增 `apps/web/src/features/diff/highlightChangedInRendered.ts`：
   - `highlightChangedInRendered(html: string, changedTexts: string[]): string`
   - 解析 HTML（DOMParser if browser，否则正则降级）
   - 在 text node 里对 `changedTexts` 做 substring match → 包 `<mark class="pd-diff-changed">`
   - 跳过 `.katex` 子树（数学原子）
   - 跳过已有 `<mark>`（不嵌套）
2. [ ] `WordHoverCard` sentence replace 模式：
   - 渲染两侧 `renderTexSentence`
   - 用当前 hunk 的 word-level DiffUnit `leftText` / `rightText` 作为 `changedTexts`
   - 左侧高亮 work 改动词，右侧高亮 compare 改动词
3. [ ] 测试：`highlightChangedInRendered.test.ts`
   - `We <strong>see</strong> x` + `["see"]` → `<mark>see</mark>` 在 `<strong>` 内
   - KaTeX span 内的 `x` 不被高亮
   - 多个改动词都高亮

**G/W/T：** Given 句子 `We introduce ...` ↔ `We study ...`，When 渲染 + 高亮，Then `introduce` / `study` 在渲染文本里被标黄。

---

### Step 6 — SentenceRenderCard 集成（S2, S6）〔P0〕

**目标：** 句级 hover 显示渲染视图 + toggle + 未编译提示。

1. [ ] `WordHoverCard.vue` 新增 sentence replace 分支：
   - 顶部 toggle `[源码 | 渲染]`（默认渲染）
   - 渲染模式：两侧 `renderTexSentence` + `highlightChangedInRendered`
   - 源码模式：现有 raw text `<code class="snip">`
   - 未编译（`ctx.compiled === false`）顶部黄条
2. [ ] `MonacoDiff.vue`：
   - 句级 hover 时把 `useTexContext(projectId).ctx` 传入 card model
   - `estimateHoverCardHeight` 句级渲染模式高度上调（~180–280px）
3. [ ] 样式：`SentenceRenderCard` 主题感知（dark / light），沿用 `MathHoverCard` 的 katex 颜色覆盖
4. [ ] 测试：组件渲染快照（渲染模式 / 源码模式 / 未编译提示）

**G/W/T：** Given 已编译项目句级 hover，When 悬停，Then 看到两侧渲染后句子 + 改动词标黄 + `[7]` 真实编号。

---

### Step 7 — 文档与声称（DoD）〔P1〕

1. [ ] `manual-smoke.md`：句级渲染矩阵全绿勾选
   - 已编译项目：渲染 + 真实编号 + 高亮
   - 未编译项目：渲染 + `[key]` 占位 + 黄条
   - toggle 切换源码 / 渲染
2. [ ] 更新 `AGENTS.md`：句级渲染状态
3. [ ] 本计划 Status → `P0 done`
4. [ ] 删除任何「引用号已完美」过誉句

---

## 4. 排期

| 步骤 | 预估 | 依赖 |
|------|------|------|
| 0 基线探查 | 1–2h | — |
| 1 aux/bbl 持久化 | 0.5d | 0 |
| 2 tex-context 解析 + 路由 | 0.5–1d | 1 |
| 3 客户端渲染器 | 1–1.5d | 2（DTO 形状） |
| 4 context 拉取缓存 | 0.5d | 2, 3 |
| 5 渲染后高亮 | 0.5–1d | 3 |
| 6 集成 SentenceRenderCard | 0.5–1d | 3, 4, 5 |
| 7 文档 | 0.5d | 1–6 |

**P0 闭环：Step 1–4 + 6**（渲染 + 真实编号，无高亮）
**P1 完整：+ Step 5**（高亮改动词）

---

## 5. 完成定义

### P0 DoD（必须）

- [ ] S3 关闭：compile 成功后 `artifacts/latest.aux` 存在
- [ ] S4 关闭：`GET /tex-context` 返回正确 `citations` / `labels`
- [ ] S5 关闭：`renderTexSentence` 单测全绿（含 XSS 防护）
- [ ] S2 关闭：句级 hover 默认渲染视图，toggle 可切源码
- [ ] 已编译项目：`\cite` 显示真实编号 `[N]`
- [ ] 未编译项目：`\cite` 显示 `[key]` + 黄条提示
- [ ] pytest + vitest + vue-tsc 全绿
- [ ] manual-smoke 句级渲染矩阵手测通过

### P1 DoD（本迭代默认）

- [ ] S6 关闭：渲染文本里改动词被 `<mark>` 标黄
- [ ] 数学部分不被内部高亮

### P2（延期）

- [ ] bibliography tooltip
- [ ] `\autoref` 真实 prefix
- [ ] 自定义命令展开

---

## 6. 延期登记

| ID | 延期原因 | 重开条件 |
|----|----------|----------|
| bibliography tooltip | R0 只需编号 | 用户 hover `[7]` 想看完整文献 |
| `\autoref` prefix | 需解析 `\autorefname` | 用户抱怨 `§` 占位不准 |
| 自定义命令展开 | 需客户端 mini preprocessor | 项目大量用 `\newcommand` |
| 跨句 footnote | `\footnotemark`/`\footnotetext` 拆开少见 | 用户反馈 |

---

## 7. 文件触点

| 区域 | 路径 |
|------|------|
| 服务端 compile | `apps/api/app/services/compile_service.py`（`_store_aux_bbl`） |
| 服务端解析 | `apps/api/app/domain/tex_context.py`（**新增**） |
| 服务端路由 | `apps/api/app/api/routes.py`（`/artifacts/aux`、`/bbl`、`/tex-context`） |
| 服务端 DTO | `apps/api/app/schemas/dto.py`（`TexContextResponse`） |
| 客户端 context 类型 | `apps/web/src/features/diff/texSentenceContext.ts`（**新增**） |
| 客户端渲染器 | `apps/web/src/features/diff/renderTexSentence.ts`（**新增**） |
| 客户端 context 拉取 | `apps/web/src/features/diff/useTexContext.ts`（**新增**） |
| 客户端高亮 | `apps/web/src/features/diff/highlightChangedInRendered.ts`（**新增**） |
| 客户端 hover card | `apps/web/src/features/diff/WordHoverCard.vue`（sentence 分支） |
| 客户端 diff mount | `apps/web/src/features/diff/MonacoDiff.vue`（传 ctx） |
| KaTeX 复用 | `apps/web/src/features/viewer/renderMathHoverHtml.ts`、`sanitizeMathLatex.ts` |
| 测试 | `test_compile_aux.py`、`test_tex_context.py`、`renderTexSentence.test.ts`、`highlightChangedInRendered.test.ts` |
| 文档 | 本文件、`manual-smoke.md`、`AGENTS.md` |

---

## 8. 与既有计划

```
comparer-preview-hardening  ── 句级 hover 已修 flip ──►  本计划加渲染层
word-hover-accept           ── 词级 hover 已闭环 ──►  本计划只动 sentence 分支
sentenceMapper              ── 句级 unit 已扩完整句 ──►  本计划消费其 leftText/rightText
renderMathHoverHtml         ── KaTeX 已集成 ──►  本计划复用 sanitizeMathLatex
compile_service             ── latexmk 已跑 ──►  本计划顺手持久化 .aux/.bbl
```

---

## 9. 执行前检查单

- [ ] 是否理解：引用号正确性 = `.aux` 的 `\bibcite` / `\newlabel`，**不**是客户端启发式？
- [ ] Step 1 是否在 compile 成功路径（非失败）才拷 `.aux`？
- [ ] Step 3 是否对 `\href{javascript:...}` 做白名单？
- [ ] Step 5 是否跳过 `.katex` 子树不内部高亮？
- [ ] Step 6 未编译时是否显示黄条而非崩溃？
- [ ] 自动化是否覆盖：已编译 / 未编译 / XSS 三场景？
- [ ] 完成后是否改过誉文档？
