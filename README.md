# grim-fusion

TypeScript monorepo that merges two Grim Dawn modding ideas:
- gdse-style automated color tagging
- grim_gleaner-style build relevance grading (F through S++)

## Monorepo layout

- `packages/core-model`: shared domain types
- `packages/color-engine`: palette and color-tag logic
- `packages/scoring-engine`: profile-weighted scoring and grade mapping
- `packages/tag-composer`: deterministic merge of color + grade tags
- `apps/cli`: local CLI entrypoint for pipeline runs

## Initial precedence rules

1. Color and grade metadata coexist by default.
2. Grade prefix is composed before the display name (for example `[S++] Item Name`).
3. Color tags wrap the final composed display tokens.
4. When both systems attempt to alter the same exact token, `tag-composer` resolves conflicts deterministically and logs the decision.

## Quick start

```powershell
cd C:\repos\grim_fusion
npm install
npm run build
npm run dev -- --example
```
