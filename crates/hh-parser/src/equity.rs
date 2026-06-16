//! All-in equity for chipEV: each player's share of the pot if the hand were run out many times
//! from the moment the last chips went in. Flop/turn/river all-ins are enumerated exhaustively;
//! preflop all-ins use seeded Monte-Carlo (deterministic — same hand always yields the same EV).
//!
//! Self-contained: a constant-time 7-card evaluator and a SplitMix64 PRNG, no external crates.

const PREFLOP_SAMPLES: usize = 20_000;

#[derive(Clone, Copy, PartialEq, Eq)]
pub struct Card {
    rank: u8, // 2..=14 (T=10, J=11, Q=12, K=13, A=14)
    suit: u8, // 0..=3
}

/// Parse the space-separated "Qd Ts" card format used in `hole_cards` / `board`.
pub fn parse_cards(s: &str) -> Option<Vec<Card>> {
    s.split_whitespace().map(parse_card).collect()
}

fn parse_card(tok: &str) -> Option<Card> {
    let b = tok.as_bytes();
    if b.len() < 2 {
        return None;
    }
    let rank = match b[0] {
        d @ b'2'..=b'9' => d - b'0',
        b'T' | b't' => 10,
        b'J' | b'j' => 11,
        b'Q' | b'q' => 12,
        b'K' | b'k' => 13,
        b'A' | b'a' => 14,
        _ => return None,
    };
    let suit = match b[1] {
        b's' | b'S' => 0,
        b'h' | b'H' => 1,
        b'd' | b'D' => 2,
        b'c' | b'C' => 3,
        _ => return None,
    };
    Some(Card { rank, suit })
}

/// Equity (win probability + split share of ties) for each player's 2-card hand, given the board
/// cards already known. Returns a vector parallel to `holes`, summing to ~1.0.
pub fn equity(holes: &[Vec<Card>], board_known: &[Card], seed: u64) -> Vec<f64> {
    let n = holes.len();
    let mut dead: Vec<Card> = Vec::new();
    for h in holes {
        dead.extend_from_slice(h);
    }
    dead.extend_from_slice(board_known);
    let deck: Vec<Card> = (0..52u8)
        .map(|i| Card { rank: i % 13 + 2, suit: i / 13 })
        .filter(|c| !dead.contains(c))
        .collect();
    let need = 5 - board_known.len();

    let mut wins = vec![0.0f64; n];
    let mut trials = 0u64;
    let mut tally = |runout: &[Card]| {
        let mut best = 0u32;
        let mut scores = [0u32; 8]; // up to 8 players (more than any Spin&Gold table)
        for (i, h) in holes.iter().enumerate() {
            let mut cs: Vec<Card> = Vec::with_capacity(7);
            cs.extend_from_slice(h);
            cs.extend_from_slice(board_known);
            cs.extend_from_slice(runout);
            let s = eval7(&cs);
            scores[i] = s;
            if s > best {
                best = s;
            }
        }
        let winners = (0..n).filter(|&i| scores[i] == best).count();
        let share = 1.0 / winners as f64;
        for i in 0..n {
            if scores[i] == best {
                wins[i] += share;
            }
        }
    };

    if need == 0 {
        tally(&[]);
        trials = 1;
    } else if need == 1 {
        for &c in &deck {
            tally(&[c]);
            trials += 1;
        }
    } else if need == 2 {
        for i in 0..deck.len() {
            for j in (i + 1)..deck.len() {
                tally(&[deck[i], deck[j]]);
                trials += 1;
            }
        }
    } else {
        // Preflop (need == 5): exhaustive C(48,5) is too slow per hand, so Monte-Carlo.
        let mut rng = SplitMix64::new(seed);
        let mut idx: Vec<usize> = (0..deck.len()).collect();
        for _ in 0..PREFLOP_SAMPLES {
            for k in 0..need {
                let r = k + (rng.next() as usize) % (idx.len() - k);
                idx.swap(k, r);
            }
            let runout: Vec<Card> = (0..need).map(|k| deck[idx[k]]).collect();
            tally(&runout);
            trials += 1;
        }
    }
    wins.iter().map(|w| w / trials as f64).collect()
}

/// Rank a 7-card hand into a comparable score (higher is better). The top bits encode the hand
/// category (8=straight flush … 0=high card); the low bits encode tie-break ranks.
fn eval7(cards: &[Card]) -> u32 {
    let mut rank_cnt = [0u8; 15];
    let mut suit_cnt = [0u8; 4];
    let mut suit_rank_mask = [0u16; 4];
    let mut rank_mask: u16 = 0;
    for c in cards {
        rank_cnt[c.rank as usize] += 1;
        suit_cnt[c.suit as usize] += 1;
        suit_rank_mask[c.suit as usize] |= 1 << c.rank;
        rank_mask |= 1 << c.rank;
    }
    let mut best = made_score(&rank_cnt, rank_mask);
    if let Some(h) = straight_high(rank_mask) {
        best = best.max(score(4, &[h, 0, 0, 0, 0]));
    }
    for s in 0..4 {
        if suit_cnt[s] >= 5 {
            best = best.max(score(5, &top_ranks(suit_rank_mask[s], 5)));
            if let Some(h) = straight_high(suit_rank_mask[s]) {
                best = best.max(score(8, &[h, 0, 0, 0, 0]));
            }
        }
    }
    best
}

fn made_score(rank_cnt: &[u8; 15], rank_mask: u16) -> u32 {
    let (mut quads, mut trips, mut pairs) = (Vec::new(), Vec::new(), Vec::new());
    for r in (2u8..=14).rev() {
        match rank_cnt[r as usize] {
            4 => quads.push(r),
            3 => trips.push(r),
            2 => pairs.push(r),
            _ => {}
        }
    }
    if let Some(&q) = quads.first() {
        let k = top_excluding(rank_mask, &[q], 1);
        return score(7, &[q, k[0], 0, 0, 0]);
    }
    if let Some(&t) = trips.first() {
        let mut pair = if trips.len() >= 2 { trips[1] } else { 0 };
        if let Some(&p) = pairs.first() {
            if p > pair {
                pair = p;
            }
        }
        if pair > 0 {
            return score(6, &[t, pair, 0, 0, 0]);
        }
        let k = top_excluding(rank_mask, &[t], 2);
        return score(3, &[t, k[0], k[1], 0, 0]);
    }
    if pairs.len() >= 2 {
        let (p1, p2) = (pairs[0], pairs[1]);
        let k = top_excluding(rank_mask, &[p1, p2], 1);
        return score(2, &[p1, p2, k[0], 0, 0]);
    }
    if let Some(&p) = pairs.first() {
        let k = top_excluding(rank_mask, &[p], 3);
        return score(1, &[p, k[0], k[1], k[2], 0]);
    }
    score(0, &top_ranks(rank_mask, 5))
}

/// Highest card of the best 5-straight in `mask` (ranks at bits 2..=14), or None. Handles the
/// wheel (A-2-3-4-5) by treating the ace as a low card.
fn straight_high(mask: u16) -> Option<u8> {
    let m = if mask & (1 << 14) != 0 { mask | (1 << 1) } else { mask };
    for high in (5u8..=14).rev() {
        if (high - 4..=high).all(|r| m & (1 << r) != 0) {
            return Some(high);
        }
    }
    None
}

fn top_ranks(mask: u16, n: usize) -> [u8; 5] {
    let mut out = [0u8; 5];
    let mut i = 0;
    for r in (2u8..=14).rev() {
        if i >= n {
            break;
        }
        if mask & (1 << r) != 0 {
            out[i] = r;
            i += 1;
        }
    }
    out
}

fn top_excluding(mask: u16, excl: &[u8], n: usize) -> [u8; 5] {
    let mut out = [0u8; 5];
    let mut i = 0;
    for r in (2u8..=14).rev() {
        if i >= n {
            break;
        }
        if mask & (1 << r) != 0 && !excl.contains(&r) {
            out[i] = r;
            i += 1;
        }
    }
    out
}

fn score(cat: u32, r: &[u8; 5]) -> u32 {
    (cat << 20)
        | ((r[0] as u32) << 16)
        | ((r[1] as u32) << 12)
        | ((r[2] as u32) << 8)
        | ((r[3] as u32) << 4)
        | (r[4] as u32)
}

struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }
    fn next(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cards(s: &str) -> Vec<Card> {
        parse_cards(s).unwrap()
    }

    #[test]
    fn aces_dominate_kings_preflop() {
        let eq = equity(&[cards("Ah As"), cards("Kh Ks")], &[], 12345);
        assert!((eq[0] - 0.82).abs() < 0.03, "AA equity {} not ~0.82", eq[0]);
        assert!((eq[0] + eq[1] - 1.0).abs() < 1e-9);
    }

    #[test]
    fn made_flush_beats_made_straight_on_river() {
        // Player A makes a flush, player B a straight; board fixed (need == 0, deterministic).
        let eq = equity(&[cards("Ah 2h"), cards("9s 8s")], &cards("Th Jh 7h 6d 5c"), 0);
        assert_eq!(eq[0], 1.0);
        assert_eq!(eq[1], 0.0);
    }

    #[test]
    fn split_pot_is_half_each() {
        // Both play the board (royal-ish straight on board) -> tie.
        let eq = equity(&[cards("2c 3d"), cards("4c 5d")], &cards("As Ks Qs Js Ts"), 0);
        assert_eq!(eq[0], 0.5);
        assert_eq!(eq[1], 0.5);
    }
}
