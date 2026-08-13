#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Item,
    Affix,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Rarity {
    Common,
    Magical,
    Rare,
    Epic,
    Legendary,
}

impl Rarity {
    /// Parses a raw `itemClassification` DB value; `None` for rarities we don't
    /// model (so the caller skips that record rather than mislabeling it). The
    /// `Broken` tier is intentionally not modeled — only 2 tags in the game have
    /// a Broken record and neither is ever colored, so we ignore those records.
    pub fn from_db(s: &str) -> Option<Self> {
        Some(match s {
            "Common" => Rarity::Common,
            "Magical" => Rarity::Magical,
            "Rare" => Rarity::Rare,
            "Epic" => Rarity::Epic,
            "Legendary" => Rarity::Legendary,
            _ => return None,
        })
    }
}
