//! Parsed hand structures plus small derivation helpers (hashing, positions).

#[derive(Debug, Clone)]
pub struct Action {
    pub street: &'static str,
    pub seat: u8,
    pub name: String,
    pub kind: &'static str, // post|fold|check|call|bet|raise
    pub amount: f64,        // chips added to pot by this action (delta)
    pub to_amount: f64,     // total street commitment after a raise (else 0)
    pub all_in: bool,
    pub index: u16,
}

#[derive(Debug, Clone)]
pub struct Player {
    pub seat: u8,
    pub name: String,
    pub is_hero: bool,
    pub villain_hash: u64,
    pub position: String,
    pub starting_stack: f64,
    pub hole_cards: String,
    pub won: f64,
    pub invested: f64,
    pub result: f64,
}

#[derive(Debug, Clone)]
pub struct Hand {
    pub hand_id: String, // deterministic UUIDv5(namespace, "tournament_id:source_hand_id")
    pub source_hand_id: String,
    pub tournament_id: String,
    pub format: &'static str, // "3max" | "6max"
    pub level: u8,
    pub small_blind: f64,
    pub big_blind: f64,
    pub played_at: String, // "YYYY-MM-DD HH:MM:SS"
    pub table_id: String,
    pub button_seat: u8,
    pub board: String,
    pub pot: f64,
    pub rake: f64,
    pub effective_stack_bb: u16, // BB * 10, hero-centric: min(hero, max opponent)
    pub players: Vec<Player>,
    pub actions: Vec<Action>,
}

/// Namespace for deterministic hand ids — must match Python's `_HAND_NS`
/// (6f9b2a1e-0c3d-5e4f-8a7b-1d2c3e4f5a6b) so Rust and Python agree on `hand_id`.
const HAND_NS: uuid::Uuid = uuid::Uuid::from_bytes([
    0x6f, 0x9b, 0x2a, 0x1e, 0x0c, 0x3d, 0x5e, 0x4f, 0x8a, 0x7b, 0x1d, 0x2c, 0x3e, 0x4f, 0x5a, 0x6b,
]);

/// Deterministic hand id: UUIDv5 of "tournament_id:source_hand_id". Re-parsing the same hand
/// yields the same id, which drives idempotent dedup.
pub fn deterministic_hand_id(tournament_id: &str, source_hand_id: &str) -> String {
    let name = format!("{tournament_id}:{source_hand_id}");
    uuid::Uuid::new_v5(&HAND_NS, name.as_bytes()).to_string()
}

/// Stable, dependency-free 64-bit hash (FNV-1a) for anonymizing opponent ids.
/// Deterministic across runs/versions; the hero maps to 0.
pub fn villain_hash(name: &str) -> u64 {
    const OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
    const PRIME: u64 = 0x0000_0100_0000_01b3;
    let mut h = OFFSET;
    for b in name.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(PRIME);
    }
    h
}

/// Quantize an effective stack in big blinds to UInt16 (BB * 10) for the ClickHouse sort key.
pub fn quantize_bb(stack: f64, big_blind: f64) -> u16 {
    if big_blind <= 0.0 {
        return 0;
    }
    let bb = (stack / big_blind) * 10.0;
    bb.round().clamp(0.0, u16::MAX as f64) as u16
}

/// Assign positions to seated players given the button seat.
///
/// `active`: seats in ascending seat-number order. Returns (seat -> position).
/// Anchors: BTN = button, SB/BB = next active seats clockwise; the remaining seats up to the
/// button are labelled with CO always immediately right of the button, then HJ, UTG going back.
/// Heads-up: button is BTN (acts as SB), the other is BB.
pub fn assign_positions(active: &[u8], button: u8) -> Vec<(u8, String)> {
    let n = active.len();
    let mut out: Vec<(u8, String)> = Vec::with_capacity(n);
    if n == 0 {
        return out;
    }
    // Clockwise order starting at the button.
    let btn_idx = active.iter().position(|&s| s == button).unwrap_or(0);
    let order: Vec<u8> = (0..n).map(|i| active[(btn_idx + i) % n]).collect();

    if n == 2 {
        out.push((order[0], "BTN".into()));
        out.push((order[1], "BB".into()));
        return out;
    }

    // order[0]=BTN, order[1]=SB, order[2]=BB, order[3..]=UTG..CO (clockwise).
    out.push((order[0], "BTN".into()));
    out.push((order[1], "SB".into()));
    out.push((order[2], "BB".into()));

    let middle = &order[3..]; // early-to-late, ending with CO just before the button
    let base = ["UTG", "HJ", "CO"];
    let k = middle.len();
    let labels: Vec<&str> = base[base.len().saturating_sub(k)..].to_vec();
    for (i, &seat) in middle.iter().enumerate() {
        let label = labels.get(i).copied().unwrap_or("MP");
        out.push((seat, label.into()));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn positions_six_max() {
        // button = seat 1; seats 1..6
        let pos = assign_positions(&[1, 2, 3, 4, 5, 6], 1);
        let map: std::collections::HashMap<u8, String> = pos.into_iter().collect();
        assert_eq!(map[&1], "BTN");
        assert_eq!(map[&2], "SB");
        assert_eq!(map[&3], "BB");
        assert_eq!(map[&4], "UTG");
        assert_eq!(map[&5], "HJ");
        assert_eq!(map[&6], "CO");
    }

    #[test]
    fn positions_three_max() {
        let pos = assign_positions(&[1, 2, 3], 1);
        let map: std::collections::HashMap<u8, String> = pos.into_iter().collect();
        assert_eq!(map[&1], "BTN");
        assert_eq!(map[&2], "SB");
        assert_eq!(map[&3], "BB");
    }

    #[test]
    fn positions_heads_up() {
        let pos = assign_positions(&[2, 3], 2);
        let map: std::collections::HashMap<u8, String> = pos.into_iter().collect();
        assert_eq!(map[&2], "BTN");
        assert_eq!(map[&3], "BB");
    }

    #[test]
    fn hero_hash_is_zero_only_when_we_choose() {
        assert_ne!(villain_hash("8be04459"), villain_hash("f55138e4"));
        assert_eq!(villain_hash("abc"), villain_hash("abc"));
    }

    #[test]
    fn quantize() {
        assert_eq!(quantize_bb(300.0, 20.0), 150); // 15bb -> 150
        assert_eq!(quantize_bb(0.0, 20.0), 0);
    }
}
