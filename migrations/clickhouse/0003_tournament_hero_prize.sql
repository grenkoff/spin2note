-- Persist hero's actual cash prize per tournament (parsed from summary finishes).
-- Enables real-money P&L: net_dollars = hero_prize - buy_in. Idempotent.
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS hero_prize Float64 AFTER hero_place;
