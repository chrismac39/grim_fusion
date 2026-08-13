function wrapColor(text, colorCode) {
    if (!colorCode) {
        return text;
    }
    return `{^${colorCode}}${text}{^w}`;
}
export function composeTag(colorized, scored) {
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
//# sourceMappingURL=index.js.map