//! Core text parsing for GG Spin&Gold hand histories.

use std::collections::HashMap;

use crate::model::{
    assign_positions, deterministic_hand_id, quantize_bb, villain_hash, Action, Hand, Player,
};

/// Split a raw blob into individual hand blocks (each starts with `Poker Hand #`).
pub fn split_hands(raw: &str) -> Vec<&str> {
    let marker = "Poker Hand #";
    let starts: Vec<usize> = raw.match_indices(marker).map(|(i, _)| i).collect();
    let mut hands = Vec::with_capacity(starts.len());
    for (i, &start) in starts.iter().enumerate() {
        let end = starts.get(i + 1).copied().unwrap_or(raw.len());
        let block = raw[start..end].trim();
        if !block.is_empty() {
            hands.push(block);
        }
    }
    hands
}

/// Table format from the `Table '...' N-max` line (falls back to seat count).
pub fn detect_block_format(block: &str) -> &'static str {
    for line in block.lines() {
        if line.starts_with("Table ") {
            if line.contains("6-max") {
                return "6max";
            }
            if line.contains("3-max") {
                return "3max";
            }
        }
    }
    let seats = block
        .lines()
        .filter(|l| l.starts_with("Seat ") && l.contains(" in chips)"))
        .count();
    if seats > 3 {
        "6max"
    } else {
        "3max"
    }
}

// --- small extraction helpers -------------------------------------------------

fn between<'a>(s: &'a str, start: &str, end: &str) -> Option<&'a str> {
    let i = s.find(start)? + start.len();
    let rest = &s[i..];
    let j = rest.find(end)?;
    Some(&rest[..j])
}

fn after<'a>(s: &'a str, start: &str) -> Option<&'a str> {
    let i = s.find(start)? + start.len();
    Some(&s[i..])
}

fn parse_f64(s: &str) -> f64 {
    // GG uses a comma thousands separator for amounts >= 1000 (e.g. "1,200").
    s.trim().replace(',', "").parse().unwrap_or(0.0)
}

/// Parse one hand block into a fully derived `Hand`.
pub fn parse_hand(block: &str) -> Option<Hand> {
    let mut lines = block.lines();
    let header = lines.next()?;

    let source_hand_id = between(header, "Poker Hand #", ":")?.trim().to_string();
    let tournament_id = between(header, "Tournament #", ",")?.trim().to_string();
    let (level, small_blind, big_blind) = parse_level(header);
    let played_at = parse_datetime(header);

    // Table line.
    let table_line = lines.next()?;
    let table_id = between(table_line, "Table '", "'").unwrap_or("").to_string();
    let format = detect_block_format(block);
    let button_seat = between(table_line, "Seat #", " is the button")
        .and_then(|s| s.trim().parse::<u8>().ok())
        .unwrap_or(0);

    // Seats + per-name index. Parsing is line-driven from here.
    let mut players: Vec<Player> = Vec::new();
    let mut seat_of: HashMap<String, u8> = HashMap::new();
    let mut idx_of_seat: HashMap<u8, usize> = HashMap::new();

    let mut board = String::new();
    let mut pot = 0.0;
    let mut rake = 0.0;

    let mut actions: Vec<Action> = Vec::new();
    let mut action_index: u16 = 0;
    let mut street: &'static str = "preflop";
    // Per-street committed chips per seat (for raise deltas); cumulative invested per seat.
    let mut committed: HashMap<u8, f64> = HashMap::new();
    let mut invested: HashMap<u8, f64> = HashMap::new();
    let mut won: HashMap<u8, f64> = HashMap::new();

    for line in block.lines().skip(2) {
        if let Some(rest) = line.strip_prefix("Seat ") {
            // "1: 8be04459 (300 in chips)"  — but skip SUMMARY seat lines (handled below).
            if rest.contains(" in chips)") {
                if let Some((seat, name, stack)) = parse_seat_line(rest) {
                    let is_hero = name == "Hero";
                    idx_of_seat.insert(seat, players.len());
                    seat_of.insert(name.clone(), seat);
                    players.push(Player {
                        seat,
                        is_hero,
                        villain_hash: if is_hero { 0 } else { villain_hash(&name) },
                        name,
                        position: String::new(),
                        starting_stack: stack,
                        hole_cards: String::new(),
                        won: 0.0,
                        invested: 0.0,
                        result: 0.0,
                    });
                }
                continue;
            }
        }

        // Street transitions.
        if line.starts_with("*** FLOP ***") {
            street = "flop";
            committed.clear();
            continue;
        } else if line.starts_with("*** TURN ***") {
            street = "turn";
            committed.clear();
            continue;
        } else if line.starts_with("*** RIVER ***") {
            street = "river";
            committed.clear();
            continue;
        } else if line.starts_with("*** HOLE CARDS ***") {
            street = "preflop";
            continue;
        } else if line.starts_with("*** ") {
            continue; // SHOWDOWN / SUMMARY / THIRD STREET etc.
        }

        // Hole cards: "Dealt to NAME [Ah Kd]"
        if let Some(rest) = line.strip_prefix("Dealt to ") {
            if let Some(cards) = between(rest, "[", "]") {
                let name = rest.split(" [").next().unwrap_or("").trim();
                if let Some(&seat) = seat_of.get(name) {
                    if let Some(&i) = idx_of_seat.get(&seat) {
                        players[i].hole_cards = cards.to_string();
                    }
                }
            }
            continue;
        }

        // Showdown reveal: "NAME: shows [cards]"
        if let Some((name, rest)) = split_name_colon(line) {
            if let Some(cards) = rest.strip_prefix("shows ").and_then(|r| between(r, "[", "]")) {
                if let Some(&seat) = seat_of.get(name) {
                    if let Some(&i) = idx_of_seat.get(&seat) {
                        players[i].hole_cards = cards.to_string();
                    }
                }
                continue;
            }
            // An action line.
            if let Some(seat) = seat_of.get(name).copied() {
                if let Some(act) = parse_action(
                    street,
                    seat,
                    name,
                    rest,
                    action_index,
                    &mut committed,
                    &mut invested,
                ) {
                    action_index += 1;
                    actions.push(act);
                }
                continue;
            }
        }

        // Uncalled bet returned.
        if let Some(rest) = line.strip_prefix("Uncalled bet (") {
            if let Some(amt) = rest.split(')').next() {
                let amount = parse_f64(amt);
                if let Some(name) = after(rest, "returned to ") {
                    if let Some(&seat) = seat_of.get(name.trim()) {
                        *invested.entry(seat).or_insert(0.0) -= amount;
                    }
                }
            }
            continue;
        }

        // Collected from pot: "NAME collected 600 from pot"
        if line.contains(" collected ") && line.ends_with(" from pot") {
            if let Some(name) = line.split(" collected ").next() {
                if let Some(amt) = between(line, " collected ", " from pot") {
                    if let Some(&seat) = seat_of.get(name.trim()) {
                        *won.entry(seat).or_insert(0.0) += parse_f64(amt);
                    }
                }
            }
            continue;
        }

        // Summary lines.
        if let Some(rest) = line.strip_prefix("Total pot ") {
            pot = parse_f64(rest.split('|').next().unwrap_or("0"));
            rake = between(line, "Rake ", " |").map(parse_f64).unwrap_or(0.0);
            continue;
        }
        if line.starts_with("Board [") {
            board = between(line, "[", "]").unwrap_or("").to_string();
            continue;
        }
    }

    if players.is_empty() {
        return None;
    }

    // Finalize per-player accounting.
    for p in players.iter_mut() {
        p.invested = *invested.get(&p.seat).unwrap_or(&0.0);
        p.won = *won.get(&p.seat).unwrap_or(&0.0);
        p.result = p.won - p.invested;
    }

    // Positions.
    let mut active: Vec<u8> = players.iter().map(|p| p.seat).collect();
    active.sort_unstable();
    let pos = assign_positions(&active, button_seat);
    let pos_map: HashMap<u8, String> = pos.into_iter().collect();
    for p in players.iter_mut() {
        if let Some(label) = pos_map.get(&p.seat) {
            p.position = label.clone();
        }
    }

    // Hero-centric effective stack: min(hero, max opponent), in BB*10.
    let effective_stack_bb = effective_stack(&players, big_blind);

    let hand_id = deterministic_hand_id(&tournament_id, &source_hand_id);

    Some(Hand {
        hand_id,
        source_hand_id,
        tournament_id,
        format,
        level,
        small_blind,
        big_blind,
        played_at,
        table_id,
        button_seat,
        board,
        pot,
        rake,
        effective_stack_bb,
        players,
        actions,
    })
}

fn effective_stack(players: &[Player], big_blind: f64) -> u16 {
    let hero = players.iter().find(|p| p.is_hero);
    let max_opp = players
        .iter()
        .filter(|p| !p.is_hero)
        .map(|p| p.starting_stack)
        .fold(0.0_f64, f64::max);
    let eff = match hero {
        Some(h) => h.starting_stack.min(if max_opp > 0.0 { max_opp } else { h.starting_stack }),
        None => players
            .iter()
            .map(|p| p.starting_stack)
            .fold(f64::INFINITY, f64::min),
    };
    quantize_bb(eff, big_blind)
}

// "1: 8be04459 (300 in chips)" -> (seat, name, stack)
fn parse_seat_line(rest: &str) -> Option<(u8, String, f64)> {
    let seat: u8 = rest.split(':').next()?.trim().parse().ok()?;
    let after_colon = after(rest, ": ")?;
    let name = after_colon.split(" (").next()?.trim().to_string();
    let stack = between(rest, "(", " in chips)").map(parse_f64)?;
    Some((seat, name, stack))
}

// Split "NAME: rest" -> (name, rest) for action/show lines (name has no ": ").
fn split_name_colon(line: &str) -> Option<(&str, &str)> {
    let idx = line.find(": ")?;
    let name = &line[..idx];
    // Exclude lines that aren't player-prefixed (e.g. start with a digit-only or markers).
    if name.is_empty() || name.contains('[') || name.starts_with('*') {
        return None;
    }
    Some((name, &line[idx + 2..]))
}

#[allow(clippy::too_many_arguments)]
fn parse_action(
    street: &'static str,
    seat: u8,
    name: &str,
    rest: &str,
    index: u16,
    committed: &mut HashMap<u8, f64>,
    invested: &mut HashMap<u8, f64>,
) -> Option<Action> {
    let all_in = rest.contains("and is all-in");
    let core = rest.split(" and is all-in").next().unwrap_or(rest).trim();

    let (kind, amount, to_amount): (&'static str, f64, f64) = if core == "folds" {
        ("fold", 0.0, 0.0)
    } else if core == "checks" {
        ("check", 0.0, 0.0)
    } else if let Some(a) = core.strip_prefix("calls ") {
        let amt = parse_f64(a);
        *committed.entry(seat).or_insert(0.0) += amt;
        *invested.entry(seat).or_insert(0.0) += amt;
        ("call", amt, 0.0)
    } else if let Some(a) = core.strip_prefix("bets ") {
        let amt = parse_f64(a);
        *committed.entry(seat).or_insert(0.0) += amt;
        *invested.entry(seat).or_insert(0.0) += amt;
        ("bet", amt, 0.0)
    } else if let Some(a) = core.strip_prefix("raises ") {
        // "raises X to Y" — Y is the new total street commitment.
        let to = a.split(" to ").nth(1).map(parse_f64).unwrap_or(0.0);
        let prev = *committed.get(&seat).unwrap_or(&0.0);
        let delta = (to - prev).max(0.0);
        committed.insert(seat, to);
        *invested.entry(seat).or_insert(0.0) += delta;
        ("raise", delta, to)
    } else if let Some(a) = core.strip_prefix("posts small blind ") {
        let amt = parse_f64(a);
        *committed.entry(seat).or_insert(0.0) += amt;
        *invested.entry(seat).or_insert(0.0) += amt;
        ("post", amt, 0.0)
    } else if let Some(a) = core.strip_prefix("posts big blind ") {
        let amt = parse_f64(a);
        *committed.entry(seat).or_insert(0.0) += amt;
        *invested.entry(seat).or_insert(0.0) += amt;
        ("post", amt, 0.0)
    } else {
        return None;
    };

    Some(Action {
        street,
        seat,
        name: name.to_string(),
        kind,
        amount,
        to_amount,
        all_in,
        index,
    })
}

// "Level1(10/20)" -> (1, 10.0, 20.0)
fn parse_level(header: &str) -> (u8, f64, f64) {
    let level = between(header, "Level", "(")
        .and_then(|s| s.trim().parse::<u8>().ok())
        .unwrap_or(0);
    let blinds = between(header, "(", ")").unwrap_or("0/0");
    let mut it = blinds.split('/');
    let sb = parse_f64(it.next().unwrap_or("0"));
    let bb = parse_f64(it.next().unwrap_or("0"));
    (level, sb, bb)
}

// "... - 2026/01/07 22:54:43" -> "2026-01-07 22:54:43"
fn parse_datetime(header: &str) -> String {
    let raw = header.rsplit(" - ").next().unwrap_or("").trim();
    // Convert date part separators to '-' for ClickHouse DateTime.
    let mut parts = raw.splitn(2, ' ');
    let date = parts.next().unwrap_or("").replace('/', "-");
    let time = parts.next().unwrap_or("00:00:00");
    format!("{date} {time}")
}

#[cfg(test)]
mod tests {
    use super::*;

    const ALLIN_SHOWDOWN: &str = "\
Poker Hand #SG3478661514: Tournament #256046646, Spin&Gold #7 Hold'em No Limit - Level1(10/20) - 2026/01/07 22:54:43
Table '16763' 3-max Seat #1 is the button
Seat 1: 8be04459 (300 in chips)
Seat 2: Hero (300 in chips)
Seat 3: f55138e4 (300 in chips)
Hero: posts small blind 10
f55138e4: posts big blind 20
*** HOLE CARDS ***
Dealt to 8be04459
Dealt to Hero [2h Ah]
Dealt to f55138e4
8be04459: folds
Hero: raises 280 to 300 and is all-in
f55138e4: calls 280 and is all-in
Hero: shows [2h Ah]
f55138e4: shows [3h 4h]
*** FLOP *** [7h 5d 4d]
*** TURN *** [7h 5d 4d] [4s]
*** RIVER *** [7h 5d 4d 4s] [9s]
*** SHOWDOWN ***
f55138e4 collected 600 from pot
*** SUMMARY ***
Total pot 600 | Rake 0 | Jackpot 0 | Bingo 0 | Fortune 0 | Tax 0
Board [7h 5d 4d 4s 9s]
Seat 1: 8be04459 (button) folded before Flop (didn't bet)
Seat 2: Hero (small blind) showed [2h Ah] and lost with a pair of Fours
Seat 3: f55138e4 (big blind) showed [3h 4h] and won (600) with three of a kind, Fours";

    #[test]
    fn parses_allin_showdown() {
        let h = parse_hand(ALLIN_SHOWDOWN).expect("hand");
        assert_eq!(h.source_hand_id, "SG3478661514");
        assert_eq!(h.tournament_id, "256046646");
        assert_eq!(h.format, "3max");
        assert_eq!(h.level, 1);
        assert_eq!(h.small_blind, 10.0);
        assert_eq!(h.big_blind, 20.0);
        assert_eq!(h.played_at, "2026-01-07 22:54:43");
        assert_eq!(h.button_seat, 1);
        assert_eq!(h.board, "7h 5d 4d 4s 9s");
        assert_eq!(h.pot, 600.0);
        assert_eq!(h.effective_stack_bb, 150); // 15bb

        let hero = h.players.iter().find(|p| p.is_hero).unwrap();
        assert_eq!(hero.position, "SB");
        assert_eq!(hero.hole_cards, "2h Ah");
        assert_eq!(hero.invested, 300.0);
        assert_eq!(hero.result, -300.0);

        let winner = h.players.iter().find(|p| p.name == "f55138e4").unwrap();
        assert_eq!(winner.position, "BB");
        assert_eq!(winner.hole_cards, "3h 4h"); // revealed at showdown
        assert_eq!(winner.won, 600.0);
        assert_eq!(winner.result, 300.0);

        // Net result across players sums to ~0 (rake 0).
        let net: f64 = h.players.iter().map(|p| p.result).sum();
        assert!(net.abs() < 1e-6);
    }

    const MULTI_STREET: &str = "\
Poker Hand #SG3478637237: Tournament #256047018, Spin&Gold #7 Hold'em No Limit - Level1(10/20) - 2026/01/07 22:55:52
Table '17028' 3-max Seat #1 is the button
Seat 1: 5bc9bc96 (300 in chips)
Seat 2: Hero (300 in chips)
Seat 3: d28a286b (300 in chips)
Hero: posts small blind 10
d28a286b: posts big blind 20
*** HOLE CARDS ***
Dealt to Hero [8d 6h]
5bc9bc96: folds
Hero: raises 20 to 40
d28a286b: calls 20
*** FLOP *** [8h Td 6s]
Hero: bets 20
d28a286b: calls 20
*** TURN *** [8h Td 6s] [Js]
Hero: bets 53
d28a286b: folds
Uncalled bet (53) returned to Hero
*** SHOWDOWN ***
Hero collected 120 from pot
*** SUMMARY ***
Total pot 120 | Rake 0 | Jackpot 0 | Bingo 0 | Fortune 0 | Tax 0
Board [8h Td 6s Js]
Seat 1: 5bc9bc96 (button) folded before Flop (didn't bet)
Seat 2: Hero (small blind) won (120)
Seat 3: d28a286b (big blind) folded on the Turn";

    #[test]
    fn parses_multistreet_with_uncalled() {
        let h = parse_hand(MULTI_STREET).expect("hand");
        let hero = h.players.iter().find(|p| p.is_hero).unwrap();
        // Invested: SB10 -> raise to 40 (delta 30) -> flop bet 20 -> turn bet 53, minus 53 uncalled.
        // 10 + 30 + 20 + 53 - 53 = 60. Won 120 -> result +60.
        assert_eq!(hero.invested, 60.0);
        assert_eq!(hero.won, 120.0);
        assert_eq!(hero.result, 60.0);

        let villain = h.players.iter().find(|p| p.name == "d28a286b").unwrap();
        // BB20 + call20(preflop, to 40) + flop call 20 = 60. Lost -> -60.
        assert_eq!(villain.invested, 60.0);
        assert_eq!(villain.result, -60.0);

        let streets: Vec<&str> = h.actions.iter().map(|a| a.street).collect();
        assert!(streets.contains(&"flop"));
        assert!(streets.contains(&"turn"));
    }

    #[test]
    fn splits_multiple_hands() {
        let raw = format!("{ALLIN_SHOWDOWN}\n\n{MULTI_STREET}");
        assert_eq!(split_hands(&raw).len(), 2);
    }

    const COMMA_POT: &str = "\
Poker Hand #SG1: Tournament #1, Spin&Gold #7 Hold'em No Limit - Level2(15/30) - 2026/01/07 23:39:03
Table '1' 3-max Seat #3 is the button
Seat 1: villainx (900 in chips)
Seat 3: Hero (600 in chips)
Hero: posts small blind 15
villainx: posts big blind 30
*** HOLE CARDS ***
Dealt to Hero [Js 9h]
Hero: raises 570 to 600 and is all-in
villainx: calls 570
*** FLOP *** [7h 5h 8c]
*** TURN *** [7h 5h 8c] [Jd]
*** RIVER *** [7h 5h 8c Jd] [8d]
*** SHOWDOWN ***
villainx collected 1,200 from pot
*** SUMMARY ***
Total pot 1,200 | Rake 0 | Jackpot 0 | Bingo 0 | Fortune 0 | Tax 0
Board [7h 5h 8c Jd 8d]
Seat 1: villainx (big blind) showed [7d 8s] and won (1,200)
Seat 3: Hero (small blind) showed [Js 9h] and lost";

    #[test]
    fn handles_comma_thousands_separator() {
        let h = parse_hand(COMMA_POT).expect("hand");
        assert_eq!(h.pot, 1200.0);
        let winner = h.players.iter().find(|p| p.name == "villainx").unwrap();
        assert_eq!(winner.won, 1200.0);
        assert_eq!(winner.result, 600.0); // won 1200 - invested 600
        let net: f64 = h.players.iter().map(|p| p.result).sum();
        assert!(net.abs() < 1e-6);
    }
}
