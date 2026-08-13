import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  applyPaletteOverrides,
  colorizeItem,
  defaultPalette,
  parsePaletteText,
} from "../../../packages/color-engine/src/index.ts";
import type { ItemRecord } from "../../../packages/core-model/src/index.ts";
import {
  parseBuildProfileText,
  scoreSemanticStatIds,
} from "../../../packages/scoring-engine/src/index.ts";
import { composeTag } from "../../../packages/tag-composer/src/index.ts";

function fixturePath(...parts: string[]): string {
  return path.join(process.cwd(), "fixtures", ...parts);
}

function readJson<T>(...parts: string[]): T {
  const raw = readFileSync(fixturePath(...parts), "utf8");
  return JSON.parse(raw) as T;
}

test("golden: gdse palette override parsing", () => {
  const text = readFileSync(fixturePath("shared", "gdse-palette.txt"), "utf8");
  const actual = parsePaletteText(text, "fixtures/shared/gdse-palette.txt");
  const expected = readJson<Record<string, string>>(
    "snapshots",
    "palette-overrides.snapshot.json"
  );

  assert.deepEqual(actual, expected);
});

test("golden: fused color + scoring output from shared fixtures", () => {
  const paletteText = readFileSync(fixturePath("shared", "gdse-palette.txt"), "utf8");
  const profileText = readFileSync(
    fixturePath("shared", "grim-gleaner-profile.json"),
    "utf8"
  );
  const items = readJson<ItemRecord[]>("shared", "items.json");

  const overrides = parsePaletteText(paletteText, "fixtures/shared/gdse-palette.txt");
  const palette = applyPaletteOverrides(defaultPalette, overrides);
  const profile = parseBuildProfileText(profileText);

  const itemResults = items.map((item) => {
    const score = scoreSemanticStatIds(
      item.stats.map((stat) => stat.key),
      profile
    );
    const tag = composeTag(colorizeItem(item, palette), {
      item,
      score: score.weightedMatch,
      grade: score.grade,
    });

    return {
      id: item.id,
      grade: score.grade,
      weightedMatch: score.weightedMatch,
      effectiveScore: Number(score.effectiveScore.toFixed(2)),
      matchedStatIds: score.matchedStatIds,
      tag: tag.displayText,
    };
  });

  const actual = {
    profile: {
      name: profile.name,
      masteries: profile.masteries,
    },
    palette: {
      legendary: palette.rarity.legendary,
      chaos: palette.damage.chaos,
    },
    items: itemResults,
  };

  const expected = readJson<object>("snapshots", "fusion-output.snapshot.json");
  assert.deepEqual(actual, expected);
});
