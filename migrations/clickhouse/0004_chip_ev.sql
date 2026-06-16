-- All-in-adjusted per-player result (chipEV). Equals `result` for hands without a 2-player all-in
-- showdown; otherwise the runout is replaced by equity*pot. Powers variance-free per-spot stats.
ALTER TABLE hand_players ADD COLUMN IF NOT EXISTS chip_ev Float64 AFTER result;
