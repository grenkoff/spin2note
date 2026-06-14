//! Tournament summary parser — provides buy-in, prize pool and the Spin&Gold multiplier.

#[derive(Debug, Clone)]
pub struct Finish {
    pub place: u16,
    pub name: String,
    pub prize: f64,
}

#[derive(Debug, Clone)]
pub struct Summary {
    pub tournament_id: String,
    pub name: String,
    pub buy_in: f64,
    pub currency: String,
    pub players: u16,
    pub prize_pool: f64,
    pub multiplier: u32, // prize_pool / buy_in, rounded (Spin&Gold prize multiplier)
    pub started_at: String,
    pub finishes: Vec<Finish>,
    pub hero_place: u16,
}

fn first_money(s: &str) -> f64 {
    // Sum every `$<number>` on the line (covers split buy-ins like "$0.23/$0.02").
    let mut total = 0.0;
    let mut rest = s;
    while let Some(i) = rest.find('$') {
        rest = &rest[i + 1..];
        let num: String = rest
            .chars()
            .take_while(|c| c.is_ascii_digit() || *c == '.' || *c == ',')
            .filter(|c| *c != ',')
            .collect();
        total += num.parse::<f64>().unwrap_or(0.0);
    }
    total
}

fn leading_u16(s: &str) -> u16 {
    s.chars()
        .take_while(|c| c.is_ascii_digit())
        .collect::<String>()
        .parse()
        .unwrap_or(0)
}

/// Split a blob of concatenated summary files into individual blocks (each starts with a
/// line `Tournament #...`). Enables bulk upload of many summaries in one request.
pub fn split_summaries(raw: &str) -> Vec<&str> {
    let mut blocks = Vec::new();
    let mut start: Option<usize> = None;
    let mut idx = 0;
    for line in raw.split_inclusive('\n') {
        if line.starts_with("Tournament #") {
            if let Some(s) = start {
                blocks.push(raw[s..idx].trim());
            }
            start = Some(idx);
        }
        idx += line.len();
    }
    if let Some(s) = start {
        blocks.push(raw[s..].trim());
    }
    blocks.into_iter().filter(|b| !b.is_empty()).collect()
}

/// Parse a blob of one or more concatenated summary files.
pub fn parse_summaries(raw: &str) -> Vec<Summary> {
    split_summaries(raw).into_iter().filter_map(parse_summary).collect()
}

pub fn parse_summary(raw: &str) -> Option<Summary> {
    let mut tournament_id = String::new();
    let mut name = String::new();
    let mut buy_in = 0.0;
    let mut currency = String::new();
    let mut players = 0u16;
    let mut prize_pool = 0.0;
    let mut started_at = String::new();
    let mut finishes: Vec<Finish> = Vec::new();
    let mut hero_place = 0u16;

    for line in raw.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("Tournament #") {
            // "256046646, Spin&Gold #7, Hold'em No Limit"
            let mut parts = rest.splitn(3, ", ");
            tournament_id = parts.next().unwrap_or("").trim().to_string();
            name = parts.next().unwrap_or("").trim().to_string();
        } else if let Some(rest) = line.strip_prefix("Buy-in: ") {
            buy_in = first_money(rest);
            currency = if rest.contains('$') { "USD".into() } else { currency };
        } else if let Some(rest) = line.strip_suffix(" Players") {
            players = leading_u16(rest.trim());
        } else if let Some(rest) = line.strip_prefix("Total Prize Pool: ") {
            prize_pool = first_money(rest);
        } else if let Some(rest) = line.strip_prefix("Tournament started ") {
            let raw_dt = rest.trim();
            let mut p = raw_dt.splitn(2, ' ');
            let date = p.next().unwrap_or("").replace('/', "-");
            let time = p.next().unwrap_or("00:00:00");
            started_at = format!("{date} {time}");
        } else if let Some(rest) = line.strip_prefix("You finished in ") {
            hero_place = leading_u16(rest);
        } else if is_finish_line(line) {
            if let Some(f) = parse_finish(line) {
                if f.name == "Hero" && hero_place == 0 {
                    hero_place = f.place;
                }
                finishes.push(f);
            }
        }
    }

    if tournament_id.is_empty() {
        return None;
    }

    let multiplier = if buy_in > 0.0 {
        (prize_pool / buy_in).round() as u32
    } else {
        0
    };

    Some(Summary {
        tournament_id,
        name,
        buy_in,
        currency,
        players,
        prize_pool,
        multiplier,
        started_at,
        finishes,
        hero_place,
    })
}

fn is_finish_line(line: &str) -> bool {
    // "3rd : Hero, $0"
    line.chars().next().map(|c| c.is_ascii_digit()).unwrap_or(false)
        && line.contains(" : ")
        && line.contains(", $")
}

fn parse_finish(line: &str) -> Option<Finish> {
    let place = leading_u16(line);
    let after = line.split(" : ").nth(1)?;
    let mut p = after.rsplitn(2, ", $");
    let prize_str = p.next().unwrap_or("0");
    let name = p.next().unwrap_or("").trim().to_string();
    Some(Finish {
        place,
        name,
        prize: prize_str.trim().parse().unwrap_or(0.0),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const SUMMARY: &str = "\
Tournament #256046646, Spin&Gold #7, Hold'em No Limit
Buy-in: $0.25
3 Players
Total Prize Pool: $0.75
Tournament started 2026/01/07 22:54:41
3rd : Hero, $0
You finished in 3rd place.";

    #[test]
    fn parses_summary() {
        let s = parse_summary(SUMMARY).expect("summary");
        assert_eq!(s.tournament_id, "256046646");
        assert_eq!(s.name, "Spin&Gold #7");
        assert_eq!(s.buy_in, 0.25);
        assert_eq!(s.players, 3);
        assert_eq!(s.prize_pool, 0.75);
        assert_eq!(s.multiplier, 3);
        assert_eq!(s.started_at, "2026-01-07 22:54:41");
        assert_eq!(s.hero_place, 3);
        assert_eq!(s.finishes.len(), 1);
        assert_eq!(s.finishes[0].name, "Hero");
        assert_eq!(s.finishes[0].prize, 0.0);
    }

    #[test]
    fn parses_concatenated_summaries() {
        let blob = format!("{SUMMARY}\n{}", SUMMARY.replace("256046646", "256046647"));
        let all = parse_summaries(&blob);
        assert_eq!(all.len(), 2);
        assert_eq!(all[0].tournament_id, "256046646");
        assert_eq!(all[1].tournament_id, "256046647");
    }
}
