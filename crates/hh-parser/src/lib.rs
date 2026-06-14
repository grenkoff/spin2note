//! High-performance GGPoker/PokerOK Spin&Gold hand-history parser (PyO3 extension).
//!
//! Parses the real GG export format for both 3-max and 6-max Spin&Gold:
//! header / table / seats / blinds / hole cards / per-street actions / showdown / summary.
//! Derives per-hand analytics (positions, hero-centric effective stack, per-player net result
//! via street-by-street contribution accounting) so the Python side only maps to domain models.
//!
//! Pure parsing lives in plain functions returning Rust structs (unit-tested without Python);
//! the `#[pyfunction]`s are thin converters to Python dicts.

mod model;
mod parser;
mod summary;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use model::{Action, Hand, Player};
use summary::Summary;

/// Detect the table format of a raw blob: `"3max"` or `"6max"` (from the first hand).
#[pyfunction]
fn detect_format(raw: &str) -> String {
    parser::split_hands(raw)
        .first()
        .map(|b| parser::detect_block_format(b))
        .unwrap_or("3max")
        .to_string()
}

/// Parse a raw hand-history blob into a list of structured hand dicts.
#[pyfunction]
fn parse<'py>(py: Python<'py>, raw: &str) -> PyResult<Bound<'py, PyList>> {
    let list = PyList::empty_bound(py);
    for block in parser::split_hands(raw) {
        if let Some(hand) = parser::parse_hand(block) {
            list.append(hand_to_py(py, &hand)?)?;
        }
    }
    Ok(list)
}

/// Parse a tournament summary file into a metadata dict.
#[pyfunction]
fn parse_summary<'py>(py: Python<'py>, raw: &str) -> PyResult<Option<Bound<'py, PyDict>>> {
    Ok(match summary::parse_summary(raw) {
        Some(s) => Some(summary_to_py(py, &s)?),
        None => None,
    })
}

/// Parse a blob of one or more concatenated summary files into a list of metadata dicts.
#[pyfunction]
fn parse_summaries<'py>(py: Python<'py>, raw: &str) -> PyResult<Bound<'py, PyList>> {
    let list = PyList::empty_bound(py);
    for s in summary::parse_summaries(raw) {
        list.append(summary_to_py(py, &s)?)?;
    }
    Ok(list)
}

fn hand_to_py<'py>(py: Python<'py>, h: &Hand) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new_bound(py);
    d.set_item("source_hand_id", &h.source_hand_id)?;
    d.set_item("tournament_id", &h.tournament_id)?;
    d.set_item("format", h.format)?;
    d.set_item("level", h.level)?;
    d.set_item("small_blind", h.small_blind)?;
    d.set_item("big_blind", h.big_blind)?;
    d.set_item("played_at", &h.played_at)?;
    d.set_item("table_id", &h.table_id)?;
    d.set_item("button_seat", h.button_seat)?;
    d.set_item("board", &h.board)?;
    d.set_item("pot", h.pot)?;
    d.set_item("rake", h.rake)?;
    d.set_item("effective_stack_bb", h.effective_stack_bb)?;

    let players = PyList::empty_bound(py);
    for p in &h.players {
        players.append(player_to_py(py, p)?)?;
    }
    d.set_item("players", players)?;

    let actions = PyList::empty_bound(py);
    for a in &h.actions {
        actions.append(action_to_py(py, a)?)?;
    }
    d.set_item("actions", actions)?;
    Ok(d)
}

fn player_to_py<'py>(py: Python<'py>, p: &Player) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new_bound(py);
    d.set_item("seat", p.seat)?;
    d.set_item("name", &p.name)?;
    d.set_item("is_hero", p.is_hero)?;
    d.set_item("villain_hash", p.villain_hash)?;
    d.set_item("position", &p.position)?;
    d.set_item("starting_stack", p.starting_stack)?;
    d.set_item("hole_cards", &p.hole_cards)?;
    d.set_item("won", p.won)?;
    d.set_item("invested", p.invested)?;
    d.set_item("result", p.result)?;
    Ok(d)
}

fn action_to_py<'py>(py: Python<'py>, a: &Action) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new_bound(py);
    d.set_item("street", a.street)?;
    d.set_item("seat", a.seat)?;
    d.set_item("name", &a.name)?;
    d.set_item("action_index", a.index)?;
    d.set_item("action_type", a.kind)?;
    d.set_item("amount", a.amount)?;
    d.set_item("to_amount", a.to_amount)?;
    d.set_item("all_in", a.all_in)?;
    Ok(d)
}

fn summary_to_py<'py>(py: Python<'py>, s: &Summary) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new_bound(py);
    d.set_item("tournament_id", &s.tournament_id)?;
    d.set_item("name", &s.name)?;
    d.set_item("buy_in", s.buy_in)?;
    d.set_item("currency", &s.currency)?;
    d.set_item("players", s.players)?;
    d.set_item("prize_pool", s.prize_pool)?;
    d.set_item("multiplier", s.multiplier)?;
    d.set_item("started_at", &s.started_at)?;
    d.set_item("hero_place", s.hero_place)?;
    let finishes = PyList::empty_bound(py);
    for f in &s.finishes {
        let fd = PyDict::new_bound(py);
        fd.set_item("place", f.place)?;
        fd.set_item("name", &f.name)?;
        fd.set_item("prize", f.prize)?;
        finishes.append(fd)?;
    }
    d.set_item("finishes", finishes)?;
    Ok(d)
}

#[pymodule]
fn hh_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(detect_format, m)?)?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(parse_summary, m)?)?;
    m.add_function(wrap_pyfunction!(parse_summaries, m)?)?;
    Ok(())
}
