import type { BuildProfile, Grade, ItemRecord, ScoredItem } from "@grim-fusion/core-model";

function gradeFromScore(score: number): Grade {
  if (score >= 18) return "S++";
  if (score >= 14) return "S+";
  if (score >= 11) return "S";
  if (score >= 8) return "A";
  if (score >= 5) return "B";
  if (score >= 3) return "C";
  if (score >= 1) return "D";
  return "F";
}

export function scoreItem(item: ItemRecord, profile: BuildProfile): ScoredItem {
  const score = item.stats.reduce((sum, stat) => {
    const weight = profile.weights[stat.key] ?? 0;
    return sum + weight;
  }, 0);

  return {
    item,
    score,
    grade: gradeFromScore(score),
  };
}
