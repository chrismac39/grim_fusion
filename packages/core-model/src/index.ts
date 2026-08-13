export type Grade =
  | "F"
  | "D"
  | "C"
  | "B"
  | "A"
  | "S"
  | "S+"
  | "S++";

export interface Palette {
  rarity: {
    common: string;
    magical: string;
    rare: string;
    epic?: string;
    legendary?: string;
  };
  damage: Record<string, string>;
  nondamage: Record<string, string>;
}

export interface BuildProfile {
  name: string;
  weights: Record<string, number>;
  masteries: [string, string];
  skillWeights: Record<string, number>;
  excludedConversionSources: Record<string, string[]>;
  resistanceCapEnabled: boolean;
  resistanceCapWeights: Record<string, number>;
}

export interface BuildProfileFile {
  schema_version: number;
  name: string;
  weights: Record<string, number>;
  masteries: [string, string];
  skill_weights: Record<string, number>;
  excluded_conversion_sources: Record<string, string[]>;
  resistance_cap_enabled: boolean;
  resistance_cap_weights: Record<string, number>;
}

export interface ItemStat {
  key: string;
  value: number;
}

export interface ItemRecord {
  id: string;
  name: string;
  rarity: "common" | "magical" | "rare" | "epic" | "legendary";
  stats: ItemStat[];
}

export interface ColoredToken {
  text: string;
  colorCode?: string;
}

export interface ColorizedItem {
  item: ItemRecord;
  tokens: ColoredToken[];
}

export interface ScoredItem {
  item: ItemRecord;
  score: number;
  grade: Grade;
}

export interface RelevanceScore {
  grade: Grade;
  weightedMatch: number;
  relevancePoints: number;
  baseEffectiveScore: number;
  profileAdjustment: number;
  effectiveScore: number;
  matchedCount: number;
  totalCategoryCount: number;
  coverageRatio: number;
  matchedStatIds: string[];
}

export interface ComposedTag {
  itemId: string;
  displayText: string;
}
