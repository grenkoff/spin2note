-- Columns and table needed by the real GG hand-history parser.
-- Additive only (no PK change). Statements separated by ';' for the /db-migrate runner.

ALTER TABLE hands
    ADD COLUMN IF NOT EXISTS source_hand_id String AFTER effective_stack_bb,
    ADD COLUMN IF NOT EXISTS tournament_id String AFTER source_hand_id,
    ADD COLUMN IF NOT EXISTS level UInt8 AFTER tournament_id,
    ADD COLUMN IF NOT EXISTS button_seat UInt8 AFTER level,
    ADD COLUMN IF NOT EXISTS rake Float64 AFTER pot;

ALTER TABLE hand_players
    ADD COLUMN IF NOT EXISTS hole_cards String AFTER position,
    ADD COLUMN IF NOT EXISTS won Float64 AFTER hole_cards;

ALTER TABLE actions
    ADD COLUMN IF NOT EXISTS to_amount Float64 AFTER pot_before,
    ADD COLUMN IF NOT EXISTS all_in UInt8 AFTER to_amount;

CREATE TABLE IF NOT EXISTS tournaments
(
    tournament_id String,
    user_id       UUID,
    name          String,
    buy_in        Float64,
    currency      LowCardinality(String),
    players       UInt16,
    prize_pool    Float64,
    multiplier    UInt32,
    started_at    Nullable(DateTime64(3)),
    hero_place    UInt16,
    parsed_at     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(parsed_at)
ORDER BY (user_id, tournament_id);
