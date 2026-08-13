import { colorizeItem, defaultPalette } from "@grim-fusion/color-engine";
import type { BuildProfile, ItemRecord } from "@grim-fusion/core-model";
import { scoreItem } from "@grim-fusion/scoring-engine";
import { composeTag } from "@grim-fusion/tag-composer";

function runExample(): void {
  const profile: BuildProfile = {
    name: "example-fire-arcanist",
    weights: {
      fire_damage_pct: 4,
      cast_speed_pct: 3,
      offensive_ability: 2,
      vitality_damage_pct: 0,
    },
  };

  const item: ItemRecord = {
    id: "sample-item-001",
    name: "Blazeseer Signet",
    rarity: "legendary",
    stats: [
      { key: "fire_damage_pct", value: 52 },
      { key: "cast_speed_pct", value: 8 },
      { key: "offensive_ability", value: 74 },
    ],
  };

  const colorized = colorizeItem(item, defaultPalette);
  const scored = scoreItem(item, profile);
  const composed = composeTag(colorized, scored);

  console.log("Profile:", profile.name);
  console.log("Item:", item.name);
  console.log("Score:", scored.score, "Grade:", scored.grade);
  console.log("Tag output:", composed.displayText);
}

if (process.argv.includes("--example") || process.argv.length === 2) {
  runExample();
}
