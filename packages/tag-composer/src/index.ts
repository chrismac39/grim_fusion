import type { ColorizedItem, ComposedTag, ScoredItem } from "@grim-fusion/core-model";

function wrapColor(text: string, colorCode?: string): string {
  if (!colorCode) {
    return text;
  }

  return `{^${colorCode}}${text}{^w}`;
}

export function composeTag(colorized: ColorizedItem, scored: ScoredItem): ComposedTag {
  if (colorized.item.id !== scored.item.id) {
    throw new Error("Cannot compose tag for mismatched items");
  }

  const gradePrefix = `[${scored.grade}]`;
  const baseText = `${gradePrefix} ${colorized.tokens.map((t) => t.text).join(" ")}`;
  const displayText = wrapColor(baseText, colorized.tokens[0]?.colorCode);

  return {
    itemId: colorized.item.id,
    displayText,
  };
}
