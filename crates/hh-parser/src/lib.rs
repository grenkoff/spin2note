//! High-performance Spin&Gold hand-history parser, exposed to Python via PyO3.
//!
//! This is the CPU-bound hot path delegated by the FastAPI backend. Currently a structural
//! skeleton: it splits a raw blob into hands and detects the table format (3-max vs 6-max).
//! Full street/action extraction for GGPoker/PokerOK formats is the next milestone — the
//! `/parse-validate` slash command snapshots this output against `testdata/{3max,6max}`.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

/// Number of `Seat N:` lines in a hand block.
fn count_seats(block: &str) -> usize {
    block
        .lines()
        .filter(|l| l.trim_start().starts_with("Seat "))
        .count()
}

/// Heuristic table-format detection. Spin&Gold is 3-max; 6-max blocks expose >3 seats.
fn detect_block_format(block: &str) -> &'static str {
    if count_seats(block) > 3 {
        "6max"
    } else {
        "3max"
    }
}

/// Split a raw blob into individual hand blocks. GGPoker hands start with `Poker Hand #`;
/// we fall back to blank-line separation so partial/sample logs still split cleanly.
fn split_hands(raw: &str) -> Vec<&str> {
    if raw.contains("Poker Hand #") {
        let mut hands = Vec::new();
        let mut start = None;
        let bytes_iter: Vec<(usize, &str)> = raw.match_indices("Poker Hand #").collect();
        for (i, (idx, _)) in bytes_iter.iter().enumerate() {
            let end = bytes_iter
                .get(i + 1)
                .map(|(next, _)| *next)
                .unwrap_or(raw.len());
            let _ = start;
            hands.push(raw[*idx..end].trim());
            start = Some(idx);
        }
        hands.into_iter().filter(|h| !h.is_empty()).collect()
    } else {
        raw.split("\n\n")
            .map(str::trim)
            .filter(|b| !b.is_empty())
            .collect()
    }
}

/// Detect the table format of a raw hand-history blob: `"3max"` or `"6max"`.
#[pyfunction]
fn detect_format(raw: &str) -> String {
    detect_block_format(raw).to_string()
}

/// Parse a raw hand-history blob into a list of structured hand dicts.
#[pyfunction]
fn parse<'py>(py: Python<'py>, raw: &str) -> PyResult<Bound<'py, PyList>> {
    let list = PyList::empty_bound(py);
    for block in split_hands(raw) {
        let hand = PyDict::new_bound(py);
        hand.set_item("format", detect_block_format(block))?;
        hand.set_item("seats", count_seats(block))?;
        hand.set_item("n_lines", block.lines().count())?;
        hand.set_item("players", PyList::empty_bound(py))?;
        hand.set_item("actions", PyList::empty_bound(py))?;
        list.append(hand)?;
    }
    Ok(list)
}

#[pymodule]
fn hh_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(detect_format, m)?)?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_three_max() {
        let block = "Seat 1: a\nSeat 2: b\nSeat 3: c";
        assert_eq!(detect_block_format(block), "3max");
    }

    #[test]
    fn detects_six_max() {
        let block = "Seat 1: a\nSeat 2: b\nSeat 3: c\nSeat 4: d\nSeat 5: e\nSeat 6: f";
        assert_eq!(detect_block_format(block), "6max");
    }

    #[test]
    fn splits_on_poker_hand_marker() {
        let raw = "Poker Hand #1\nSeat 1: a\n\nPoker Hand #2\nSeat 1: b";
        assert_eq!(split_hands(raw).len(), 2);
    }
}
