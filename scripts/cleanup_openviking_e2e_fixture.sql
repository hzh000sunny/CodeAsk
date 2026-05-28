-- Remove OpenViking dashboard live-E2E fixture rows from a local data database.
-- Usage:
--   sqlite3 "$CODEASK_DATA_DIR/data.db" < scripts/cleanup_openviking_e2e_fixture.sql

DELETE FROM openviking_dashboard_events WHERE source_type = 'e2e_unknown';
DELETE FROM openviking_sync_jobs WHERE source_type = 'e2e_unknown';
