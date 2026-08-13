function gradeFromScore(score) {
    if (score >= 18)
        return "S++";
    if (score >= 14)
        return "S+";
    if (score >= 11)
        return "S";
    if (score >= 8)
        return "A";
    if (score >= 5)
        return "B";
    if (score >= 3)
        return "C";
    if (score >= 1)
        return "D";
    return "F";
}
export function scoreItem(item, profile) {
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
//# sourceMappingURL=index.js.map