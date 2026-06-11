-- Spin&Gold analytics schema (UUIDv7 ids, 3-max/6-max).
-- Primary key per CLAUDE.md §2.2: (user_id, tournament_format, effective_stack, hand_id).
-- Time-range scans use played_at (ClickHouse does not sort UUIDv7 chronologically).
-- Statements are separated by ';' and applied by the /db-migrate runner.

CREATE TABLE IF NOT EXISTS hands
(
    hand_id            UUID,
    user_id            UUID,
    tournament_format  Enum8('3max' = 3, '6max' = 6),
    effective_stack_bb UInt16,
    played_at          DateTime64(3),
    multiplier         Float32,
    small_blind        Float32,
    big_blind          Float32,
    board              String,
    pot                Float64,
    parsed_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(parsed_at)
PARTITION BY toYYYYMM(played_at)
ORDER BY (user_id, tournament_format, effective_stack_bb, hand_id);

CREATE TABLE IF NOT EXISTS hand_players
(
    hand_id            UUID,
    user_id            UUID,
    tournament_format  Enum8('3max' = 3, '6max' = 6),
    effective_stack_bb UInt16,
    seat               UInt8,
    is_hero            UInt8,
    villain_hash       UInt64,
    position           LowCardinality(String),
    starting_stack     Float64,
    result             Float64,
    parsed_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(parsed_at)
PARTITION BY tournament_format
ORDER BY (user_id, tournament_format, effective_stack_bb, hand_id, seat);

CREATE TABLE IF NOT EXISTS actions
(
    hand_id            UUID,
    user_id            UUID,
    tournament_format  Enum8('3max' = 3, '6max' = 6),
    effective_stack_bb UInt16,
    street             Enum8('preflop' = 1, 'flop' = 2, 'turn' = 3, 'river' = 4),
    seat               UInt8,
    action_index       UInt16,
    action_type        Enum8('fold' = 1, 'check' = 2, 'call' = 3, 'bet' = 4, 'raise' = 5, 'all_in' = 6, 'post' = 7),
    amount             Float64,
    pot_before         Float64
)
ENGINE = MergeTree
PARTITION BY tournament_format
ORDER BY (user_id, tournament_format, effective_stack_bb, hand_id, action_index);

CREATE TABLE IF NOT EXISTS hud_stats
(
    user_id            UUID,
    tournament_format  Enum8('3max' = 3, '6max' = 6),
    effective_stack_bb UInt16,
    position           LowCardinality(String),
    hands              UInt64,
    total_result       Float64
)
ENGINE = SummingMergeTree
ORDER BY (user_id, tournament_format, effective_stack_bb, position);

CREATE MATERIALIZED VIEW IF NOT EXISTS hud_stats_mv TO hud_stats AS
SELECT
    user_id,
    tournament_format,
    effective_stack_bb,
    position,
    count() AS hands,
    sum(result) AS total_result
FROM hand_players
GROUP BY user_id, tournament_format, effective_stack_bb, position;

CREATE TABLE IF NOT EXISTS gto_solutions
(
    tournament_format  Enum8('3max' = 3, '6max' = 6),
    effective_stack_bb UInt16,
    position           LowCardinality(String),
    action_seq         String,
    action             Enum8('fold' = 1, 'check' = 2, 'call' = 3, 'bet' = 4, 'raise' = 5, 'all_in' = 6),
    frequency          Float32,
    ev                 Float32
)
ENGINE = ReplacingMergeTree
ORDER BY (tournament_format, effective_stack_bb, position, action_seq, action);

CREATE TABLE IF NOT EXISTS trainer_mistakes
(
    mistake_id         UUID,
    user_id            UUID,
    tournament_format  Enum8('3max' = 3, '6max' = 6),
    effective_stack_bb UInt16,
    position           LowCardinality(String),
    action_seq         String,
    chosen_action      Enum8('fold' = 1, 'check' = 2, 'call' = 3, 'bet' = 4, 'raise' = 5, 'all_in' = 6),
    gto_action         Enum8('fold' = 1, 'check' = 2, 'call' = 3, 'bet' = 4, 'raise' = 5, 'all_in' = 6),
    ev_delta           Float32,
    created_at         DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (user_id, tournament_format, effective_stack_bb, created_at);
