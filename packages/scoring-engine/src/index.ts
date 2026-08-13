import type {
  BuildProfile,
  BuildProfileFile,
  Grade,
  ItemRecord,
  RelevanceScore,
  ScoredItem,
} from "@grim-fusion/core-model";

const PROFILE_FILE_SCHEMA_VERSION = 4;
const SUPPORTED_PROFILE_SCHEMA_VERSIONS = new Set([1, 2, 3, 4]);

const GRADE_THRESHOLDS: Array<[Grade, number]> = [
  ["S++", 24.0],
  ["S+", 18.0],
  ["S", 14.0],
  ["A", 10.0],
  ["B", 6.0],
  ["C", 3.0],
  ["D", 1.0],
];

const REFERENCE_PROFILE_INTENSITY = 1.875;
const MIN_PROFILE_ADJUSTMENT = 0.8;
const MAX_PROFILE_ADJUSTMENT = 1.25;
const FULL_ADJUSTMENT_WEIGHT_COUNT = 8;

export class ProfileFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProfileFormatError";
  }
}

function assertWeight(value: unknown, where: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 4) {
    throw new ProfileFormatError(`${where} must be an integer from 0 to 4`);
  }
  return value;
}

function canonicalSkillReference(reference: string): string {
  const normalized = reference.trim().toLowerCase().replace(/\\/g, "/");
  if (normalized.endsWith("_buff.dbr")) {
    return `${normalized.slice(0, -"_buff.dbr".length)}.dbr`;
  }
  return normalized;
}

function gradeFromEffectiveScore(score: number): Grade {
  for (const [grade, threshold] of GRADE_THRESHOLDS) {
    if (score >= threshold) {
      return grade;
    }
  }
  return "F";
}

function pointsForWeight(weight: number): number {
  return (weight * weight) / 4;
}

export function profileScoreAdjustment(profile: BuildProfile): number {
  const nonzeroWeights = [
    ...Object.values(profile.weights).filter((weight) => weight > 0),
    ...Object.values(profile.skillWeights).filter((weight) => weight > 0),
  ];

  if (nonzeroWeights.length === 0) {
    return 1.0;
  }

  const intensity =
    nonzeroWeights.reduce((sum, weight) => sum + pointsForWeight(weight), 0) /
    nonzeroWeights.length;
  const raw = Math.sqrt(REFERENCE_PROFILE_INTENSITY / intensity);
  const bounded = Math.min(MAX_PROFILE_ADJUSTMENT, Math.max(MIN_PROFILE_ADJUSTMENT, raw));
  const confidence = Math.min(nonzeroWeights.length / FULL_ADJUSTMENT_WEIGHT_COUNT, 1.0);

  return 1.0 + (bounded - 1.0) * confidence;
}

export function profileWeightForSemanticId(profile: BuildProfile, semanticStatId: string): number {
  for (const prefix of ["skill_bonus:", "skill_modifier:"]) {
    if (!semanticStatId.startsWith(prefix)) {
      continue;
    }

    const target = canonicalSkillReference(semanticStatId.slice(prefix.length));
    let best = 0;
    for (const [skillId, weight] of Object.entries(profile.skillWeights)) {
      if (canonicalSkillReference(skillId) === target) {
        best = Math.max(best, weight);
      }
    }
    return best;
  }

  const masteryPrefix = "mastery_bonus:";
  if (semanticStatId.startsWith(masteryPrefix)) {
    const masteryId = semanticStatId.slice(masteryPrefix.length);
    return profile.masteries.includes(masteryId) ? 4 : 0;
  }

  return profile.weights[semanticStatId] ?? 0;
}

export function scoreSemanticStatIds(statIds: string[], profile: BuildProfile): RelevanceScore {
  const uniqueStatIds = Array.from(new Set(statIds));
  const matched = uniqueStatIds
    .filter((statId) => profileWeightForSemanticId(profile, statId) > 0)
    .sort((a, b) => {
      const aw = profileWeightForSemanticId(profile, a);
      const bw = profileWeightForSemanticId(profile, b);
      if (aw !== bw) {
        return bw - aw;
      }
      return a.localeCompare(b);
    });

  const weightedMatch = matched.reduce(
    (sum, statId) => sum + profileWeightForSemanticId(profile, statId),
    0
  );
  const relevancePoints = matched.reduce(
    (sum, statId) => sum + pointsForWeight(profileWeightForSemanticId(profile, statId)),
    0
  );
  const matchedCount = matched.length;
  const totalCategoryCount = uniqueStatIds.length;
  const coverageRatio = totalCategoryCount === 0 ? 0 : matchedCount / totalCategoryCount;
  const coverageMultiplier = 0.7 + 0.3 * coverageRatio;
  const baseEffectiveScore = relevancePoints * coverageMultiplier;
  const adjustment = profileScoreAdjustment(profile);
  const effectiveScore = baseEffectiveScore * adjustment;

  return {
    grade: gradeFromEffectiveScore(effectiveScore),
    weightedMatch,
    relevancePoints,
    baseEffectiveScore,
    profileAdjustment: adjustment,
    effectiveScore,
    matchedCount,
    totalCategoryCount,
    coverageRatio,
    matchedStatIds: matched,
  };
}

function assertRecordOfInt(
  value: unknown,
  where: string
): Record<string, number> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ProfileFormatError(`${where} must be an object`);
  }
  const out: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (!key.trim()) {
      throw new ProfileFormatError(`${where} contains a blank key`);
    }
    out[key] = assertWeight(raw, `${where}.${key}`);
  }
  return out;
}

export function parseBuildProfileText(text: string): BuildProfile {
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new ProfileFormatError(`Could not parse profile JSON: ${String(error)}`);
  }

  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new ProfileFormatError("Profile file must contain a JSON object");
  }

  const raw = payload as Partial<BuildProfileFile>;
  if (
    typeof raw.schema_version !== "number" ||
    !SUPPORTED_PROFILE_SCHEMA_VERSIONS.has(raw.schema_version)
  ) {
    throw new ProfileFormatError(
      `Unsupported profile schema version: ${String(raw.schema_version)}`
    );
  }

  const name = typeof raw.name === "string" ? raw.name : "New Build Profile";
  const masteriesRaw = raw.masteries ?? ["", ""];
  if (!Array.isArray(masteriesRaw) || masteriesRaw.length !== 2) {
    throw new ProfileFormatError("profile masteries must be a two-item array");
  }

  const masteries: [string, string] = [String(masteriesRaw[0] ?? ""), String(masteriesRaw[1] ?? "")];
  const weights = assertRecordOfInt(raw.weights ?? {}, "weights");
  const skillWeights = assertRecordOfInt(raw.skill_weights ?? {}, "skill_weights");
  const resistanceCapWeights = assertRecordOfInt(
    raw.resistance_cap_weights ?? {},
    "resistance_cap_weights"
  );

  const resistanceCapEnabled = Boolean(raw.resistance_cap_enabled ?? false);
  const excludedRaw = raw.excluded_conversion_sources ?? {};
  if (typeof excludedRaw !== "object" || excludedRaw === null || Array.isArray(excludedRaw)) {
    throw new ProfileFormatError("excluded_conversion_sources must be an object");
  }

  const excludedConversionSources: Record<string, string[]> = {};
  for (const [destination, sources] of Object.entries(excludedRaw)) {
    if (!Array.isArray(sources) || !sources.every((item) => typeof item === "string")) {
      throw new ProfileFormatError(
        `excluded_conversion_sources.${destination} must be a string array`
      );
    }
    excludedConversionSources[destination] = [...sources].sort();
  }

  return {
    name,
    weights,
    masteries,
    skillWeights,
    excludedConversionSources,
    resistanceCapEnabled,
    resistanceCapWeights,
  };
}

export function serializeBuildProfile(profile: BuildProfile): BuildProfileFile {
  return {
    schema_version: PROFILE_FILE_SCHEMA_VERSION,
    name: profile.name,
    masteries: profile.masteries,
    skill_weights: Object.fromEntries(Object.entries(profile.skillWeights).sort()),
    weights: Object.fromEntries(Object.entries(profile.weights).sort()),
    resistance_cap_enabled: profile.resistanceCapEnabled,
    resistance_cap_weights: Object.fromEntries(
      Object.entries(profile.resistanceCapWeights).sort()
    ),
    excluded_conversion_sources: Object.fromEntries(
      Object.entries(profile.excludedConversionSources)
        .map(([k, v]) => [k, [...v].sort()] as const)
        .sort(([a], [b]) => a.localeCompare(b))
    ),
  };
}

export function scoreItem(item: ItemRecord, profile: BuildProfile): ScoredItem {
  const relevance = scoreSemanticStatIds(item.stats.map((stat) => stat.key), profile);
  return {
    item,
    score: relevance.weightedMatch,
    grade: relevance.grade,
  };
}
