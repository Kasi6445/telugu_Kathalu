# Hardening Follow-ups

## Tracking policy

These items are tracked separately from the hardening work (cost tracker, tests,
threading safety, routing enforcement) and should be addressed in a dedicated
cleanup PR after:

- Billing case **70914394** resolves
- Phase 4 (Vertex AI smoke test) completes
- Phase 5 (full story audit) completes

**Priority: low** — no runtime impact, type-checker noise only. The pipeline
runs correctly. These are suppressed by the absence of a strict pyright baseline
and do not block any CI gate today.

---

## Type-checker debt — 17 pyright errors

Recorded from `pyright lib/` run on 2026-05-07. All errors are in two files:
`lib/balancer.py` (1) and `lib/image_gen.py` (16).

---

### lib/balancer.py

| # | Line | Error nature | Pre-existing or refactor-induced | Suggested fix |
|---|------|-------------|----------------------------------|---------------|
| 1 | 72:23 | `json.loads()` receives `str \| Unknown \| None`; `None` not guarded before call (`reportArgumentType`) | Pre-existing | Add `if raw is None: continue` (or equivalent) before the `json.loads(raw)` call |

---

### lib/image_gen.py

| # | Line | Error nature | Pre-existing or refactor-induced | Suggested fix |
|---|------|-------------|----------------------------------|---------------|
| 2 | 77:12 | Return type inferred as `CostTrackedClient \| Client`, declared as `Client` (`reportReturnType`) | **Refactor-induced** — `make_client()` now returns a union after bypass refactor | Change return annotation to `Client \| CostTrackedClient`, or introduce a `Protocol`/`TypeAlias` in `lib/config.py` |
| 3 | 116:25 | `None` not subscriptable — `response.candidates[0]` accessed without None guard (`reportOptionalSubscript`) | Pre-existing | Guard with `if response.candidates` before subscript |
| 4 | 116:25 | `None` not iterable — same `response.candidates` site (`reportOptionalIterable`) | Pre-existing | Same guard as #3 (fixes both) |
| 5 | 116:52 | `"parts"` not a known attribute of `None` — `candidates[0].content` may be None (`reportOptionalMemberAccess`) | Pre-existing | Guard with `if c.content` before accessing `.parts` |
| 6 | 117:76 | `"data"` not a known attribute of `None` — `part.inline_data` may be None (`reportOptionalMemberAccess`) | Pre-existing | Guard with `if part.inline_data` before accessing `.data` |
| 7 | 265:18 | `list[Part]` not assignable to `ContentListUnionDict` parameter of `generate_content` (`reportArgumentType`) | Pre-existing | Wrap in `types.Content(parts=...)` or cast to the accepted union type |
| 8 | 271:17 | Same as #3 — second call site with `response.candidates` (`reportOptionalSubscript`) | Pre-existing | Same guard pattern |
| 9 | 271:17 | Same as #4 — second call site (`reportOptionalIterable`) | Pre-existing | Same guard pattern |
| 10 | 271:48 | Same as #5 — second call site (`reportOptionalMemberAccess`) | Pre-existing | Same guard pattern |
| 11 | 272:68 | Same as #6 — second call site `part.inline_data.data` (`reportOptionalMemberAccess`) | Pre-existing | Guard with `if part.inline_data` |
| 12 | 274:54 | `part.inline_data.data` — third access, same Optional chain (`reportOptionalMemberAccess`) | Pre-existing | Same guard as #11 |
| 13 | 292:29 | `Literal['BLOCK_ONLY_HIGH']` not assignable to `SafetyFilterLevel \| None` — string passed where enum expected (`reportArgumentType`) | Pre-existing | Replace string with `types.SafetyFilterLevel.BLOCK_ONLY_HIGH` |
| 14 | 293:27 | `Literal['ALLOW_ALL']` not assignable to `PersonGeneration \| None` — same string-vs-enum pattern (`reportArgumentType`) | Pre-existing | Replace string with `types.PersonGeneration.ALLOW_ALL` |
| 15 | 320:41 | `bytes \| None` not assignable to `ReadableBuffer` — `image.image_bytes` may be None (`reportArgumentType`) | Pre-existing | Guard with `if image.image_bytes` before `write_bytes()` call |
| 16 | 375:65 | `str \| None` not assignable to `str` — optional model name passed to `_call_gemini_generate` (`reportArgumentType`) | Pre-existing | Add `assert model is not None` or default before the call |
| 17 | 476:31 | `LANCZOS` not a known attribute of `PIL.Image` (`reportAttributeAccessIssue`) | Pre-existing | Use `PIL.Image.Resampling.LANCZOS` (Pillow ≥ 9.1 renamed it) |

---

## Summary

| File | Pre-existing | Refactor-induced |
|------|-------------|-----------------|
| `lib/balancer.py` | 1 | 0 |
| `lib/image_gen.py` | 15 | 1 (#2 — return type union) |
| **Total** | **16** | **1** |

The one refactor-induced error (#2) is cosmetic: `CostTrackedClient` is a
transparent wrapper that passes through all `Client` attributes, so it is
safe at runtime. The correct long-term fix is a shared `Protocol` or
`TypeAlias` in `lib/config.py` that both `Client` and `CostTrackedClient`
satisfy — do this alongside any future `lib/image_gen.py` cleanup pass.
