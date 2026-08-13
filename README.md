# grim-fusion

TypeScript monorepo that merges two Grim Dawn modding ideas:
- Rainbow filter inspires gdse-style automated damage type colorization
- grim_gleaner-style build relevance grading (F through S++)

## Monorepo layout

- `packages/core-model`: shared domain types
- `packages/color-engine`: palette and color-tag logic
- `packages/scoring-engine`: profile-weighted scoring and grade mapping
- `packages/tag-composer`: deterministic merge of color + grade tags
- `apps/cli`: local CLI entrypoint for pipeline runs
- `vendor/grim_gleaner`: vendored Python UI/scoring source used by fusion session flow
- `vendor/gdse`: vendored Rust source (including your feature-branch extensions) used as reference and parity target

This repo is now self-contained. grim_fusion defaults to vendored sources and does not require cross-repo calls.

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

`npm install` now bootstraps grim_gleaner dependencies automatically:

- verifies Python 3.13
- installs Python 3.13 via `winget` on Windows if missing
- installs `grim_gleaner` editable package plus `PySide6`

The editable install target is `vendor\grim_gleaner` by default.

By default it uses the vendored copy at `vendor\grim_gleaner` inside this repo.
No sibling-repo lookup is required.

You can rerun bootstrap manually at any time:

```powershell
npm run setup:deps
```

## Current unified workflow

Use grim_gleaner to build or edit a profile, then run fusion output with gdse palette logic.

### One-command guided session

This follows the intended end-user flow:

1. Ask for Grim Dawn install path.
2. Verify Python and grim_gleaner UI dependencies.
3. Launch grim_gleaner UI for profile creation/editing.
4. Ask default/custom gdse palette.
5. Save a named build plan.
6. Let you choose a plan and apply generated text into `settings/text_en`.

```powershell
npm run dev -- session --grim-dawn-path "C:\Program Files (x86)\Steam\steamapps\common\Grim Dawn"
```

The session command also writes hash history in `settings/gdse-db-hash.txt` using gdse-compatible line format:

`<YYYY-MM-DD HH:MM> hash=<sha256> steam_build_id=<id_or_unknown> patch_versions=<list_or_unknown>`

Saved plans are stored in `artifacts/plans/*.json` and now include generation metadata:

- source profile hash
- source items hash (db-style input hash)
- optional custom palette hash
- fusion output hash
- steam build id
- inferred patch markers

If current Steam build, patch markers, or source hashes differ when applying a plan,
fusion prints a regeneration warning before applying.

### Fast character/profile switching

Once plans exist, you can switch builds without reopening the UI:

```powershell
npm run dev -- apply-plan --plan-name "Chaos Purifier"
```

Or run without `--plan-name` to choose from an interactive list:

```powershell
npm run dev -- apply-plan
```

1. Run fusion directly with a known profile JSON:

```powershell
npm run dev -- run --profile C:\path\to\profile.json --items fixtures\shared\items.json --palette fixtures\shared\gdse-palette.txt --out fusion-output.json
```

2. Launch grim_gleaner UI first, then run fusion immediately after the UI closes:

```powershell
npm run dev -- run-with-gleaner --profile C:\path\to\profile.json --items fixtures\shared\items.json --palette fixtures\shared\gdse-palette.txt --out fusion-output.json
```

3. If you save a profile in a folder and want auto-pick of the newest JSON:

```powershell
npm run dev -- run-with-gleaner --profile-dir vendor\grim_gleaner\artifacts\profiles\examples --items fixtures\shared\items.json --palette fixtures\shared\gdse-palette.txt
```
