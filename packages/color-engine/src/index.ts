import { readFileSync } from "node:fs";

import type { ColorizedItem, ItemRecord, Palette } from "@grim-fusion/core-model";

const KNOWN_PALETTE_KEYS = new Set([
  "rarity.common",
  "rarity.magical",
  "rarity.rare",
  "rarity.epic",
  "rarity.legendary",
  "damage.physical",
  "damage.pierce",
  "damage.bleeding",
  "damage.fire",
  "damage.cold",
  "damage.lightning",
  "damage.poison",
  "damage.vitality",
  "damage.life",
  "damage.aether",
  "damage.chaos",
  "damage.elemental",
  "nondamage.attribute0",
  "nondamage.mastery_increment",
  "nondamage.all_skill_increment",
  "nondamage.run_speed",
  "nondamage.cast_speed",
  "nondamage.attack_speed",
  "nondamage.total_speed",
  "nondamage.run_speed_modifier",
  "nondamage.offensive_ability",
  "nondamage.defensive_ability",
  "nondamage.crit_damage",
  "nondamage.damage_mult",
  "nondamage.total_damage",
]);

export class PaletteParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PaletteParseError";
  }
}

export type PaletteOverrideMap = Record<string, string>;

function pickRarityColor(item: ItemRecord, palette: Palette): string | undefined {
  if (item.rarity === "epic") {
    return palette.rarity.epic;
  }

  if (item.rarity === "legendary") {
    return palette.rarity.legendary;
  }

  return palette.rarity[item.rarity];
}

export function colorizeItem(item: ItemRecord, palette: Palette): ColorizedItem {
  return {
    item,
    tokens: [
      {
        text: item.name,
        colorCode: pickRarityColor(item, palette),
      },
    ],
  };
}

function parseColorCode(raw: string): string {
  const trimmed = raw.trim().toLowerCase();
  if (!/^[a-z]$/.test(trimmed)) {
    throw new PaletteParseError(
      `Invalid color code '${raw}'. Use one letter like w, y, g, f, r.`
    );
  }
  return trimmed;
}

export function parsePaletteText(text: string, sourceName = "palette"): PaletteOverrideMap {
  const overrides: PaletteOverrideMap = {};
  const lines = text.split(/\r?\n/);

  for (let i = 0; i < lines.length; i += 1) {
    const lineNumber = i + 1;
    const line = lines[i].trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const eq = line.indexOf("=");
    if (eq < 0) {
      throw new PaletteParseError(
        `Invalid palette line ${lineNumber} in ${sourceName}: expected key=value`
      );
    }

    const key = line.slice(0, eq).trim().toLowerCase();
    const value = line.slice(eq + 1).trim();

    if (!KNOWN_PALETTE_KEYS.has(key)) {
      throw new PaletteParseError(
        `Unknown palette key '${key}' on line ${lineNumber} in ${sourceName}`
      );
    }

    overrides[key] = parseColorCode(value);
  }

  return overrides;
}

export function loadPaletteOverridesFromFile(path: string): PaletteOverrideMap {
  const text = readFileSync(path, "utf8");
  return parsePaletteText(text, path);
}

export function applyPaletteOverrides(basePalette: Palette, overrides: PaletteOverrideMap): Palette {
  const next: Palette = {
    rarity: { ...basePalette.rarity },
    damage: { ...basePalette.damage },
    nondamage: { ...basePalette.nondamage },
  };

  for (const [key, color] of Object.entries(overrides)) {
    const [group, subkey] = key.split(".");
    if (group === "rarity") {
      if (subkey === "common" || subkey === "magical" || subkey === "rare") {
        next.rarity[subkey] = color;
      } else if (subkey === "epic" || subkey === "legendary") {
        next.rarity[subkey] = color;
      }
      continue;
    }

    if (group === "damage") {
      next.damage[subkey] = color;
      continue;
    }

    if (group === "nondamage") {
      next.nondamage[subkey] = color;
    }
  }

  return next;
}

export const defaultPalette: Palette = {
  rarity: {
    common: "w",
    magical: "y",
    rare: "g",
    epic: undefined,
    legendary: undefined,
  },
  damage: {
    physical: "k",
    pierce: "f",
    bleeding: "r",
    fire: "o",
    cold: "c",
    lightning: "z",
    poison: "l",
    vitality: "m",
    life: "m",
    aether: "a",
    chaos: "p",
    elemental: "y",
  },
  nondamage: {
    attribute0: "h",
    mastery_increment: "t",
    all_skill_increment: "t",
  },
};
