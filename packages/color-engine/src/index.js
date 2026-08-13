function pickRarityColor(item, palette) {
    if (item.rarity === "epic") {
        return palette.rarity.epic;
    }
    if (item.rarity === "legendary") {
        return palette.rarity.legendary;
    }
    return palette.rarity[item.rarity];
}
export function colorizeItem(item, palette) {
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
export const defaultPalette = {
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
//# sourceMappingURL=index.js.map