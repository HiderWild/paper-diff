# Word hover-accept tier × swap matrix (Phase 4)

| Tier | `wordUnits` | Hover card | Notes |
|------|-------------|------------|--------|
| **S** | true | **On** (if settings `wordHoverAccept`) | Full word + sentence units from `buildDiffUnits` |
| **M** | **false** (v1) | **Off** | Kept off until viewport-limited decorations exist |
| **L** | false | Off | No word units; arrows may still show for hunks |

| Display | Hit-test / labels |
|---------|-------------------|
| Normal | original=work, modified=compare |
| `sidesSwapped` | visual flip; card always 工作区/对照 true-source |

**Manual smoke:** small dual-side `.tex`/text, hover word → Apply → Undo; toggle swap; settings kill switch.
