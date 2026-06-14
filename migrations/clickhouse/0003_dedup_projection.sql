-- Speed up input deduplication at scale: a projection ordered by (user_id, hand_id) turns the
-- membership query `... WHERE user_id = X AND hand_id IN (...)` into an index seek instead of a
-- scan of the user's partition (the base PK ends with hand_id behind format/effective_stack).
--
-- `hands` is a ReplacingMergeTree, so CH 24.8 requires deduplicate_merge_projection_mode to be
-- set before a projection is allowed; 'rebuild' rebuilds the projection from deduplicated data
-- on merge. Statements are separated by ';' for the /db-migrate runner.

ALTER TABLE hands MODIFY SETTING deduplicate_merge_projection_mode = 'rebuild';

ALTER TABLE hands
    ADD PROJECTION IF NOT EXISTS p_user_hand
    (SELECT user_id, hand_id ORDER BY (user_id, hand_id));

ALTER TABLE hands MATERIALIZE PROJECTION p_user_hand;
