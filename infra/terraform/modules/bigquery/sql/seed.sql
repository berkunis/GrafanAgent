-- Idempotent seed for the GrafanAgent demo dataset.
-- Re-running this is safe: each block deletes its target rows by id before inserting.

-- ---- users -----------------------------------------------------------------
DELETE FROM `${project}.${dataset}.users` WHERE user_id IN ('user-aha-001', 'user-mql-002', 'user-attr-003');

INSERT INTO `${project}.${dataset}.users`
  (user_id,        email,                          plan,    company,         country, signed_up_at,                  first_active_at,               lifecycle_stage)
VALUES
  ('user-aha-001', 'priya.shah@example.test',      'free',  'Lattice Loop',  'US',    TIMESTAMP '2026-03-12 14:01:00 UTC', TIMESTAMP '2026-03-12 14:08:00 UTC', 'activated'),
  ('user-mql-002', 'amir.koroma@example.test',     'free',  'NorthFold Inc', 'CA',    TIMESTAMP '2026-02-04 09:30:00 UTC', TIMESTAMP '2026-02-04 09:42:00 UTC', 'mql'),
  ('user-attr-003','rosa.mendez@example.test',     'team',  'Driftwave',     'MX',    TIMESTAMP '2025-11-19 18:21:00 UTC', TIMESTAMP '2025-11-19 18:30:00 UTC', 'customer');

-- ---- usage_events ----------------------------------------------------------
DELETE FROM `${project}.${dataset}.usage_events` WHERE user_id IN ('user-aha-001', 'user-mql-002', 'user-attr-003');

INSERT INTO `${project}.${dataset}.usage_events`
  (event_id,   user_id,        event_type,            value, occurred_at,                          context)
VALUES
  ('evt-001',  'user-aha-001', 'dashboard_created',    1.0,  TIMESTAMP '2026-04-13 10:14:00 UTC', JSON '{"dashboard_kind":"latency"}'),
  ('evt-002',  'user-aha-001', 'alert_configured',     1.0,  TIMESTAMP '2026-04-13 10:21:00 UTC', JSON '{"channel":"slack"}'),
  ('evt-003',  'user-aha-001', 'integration_added',    1.0,  TIMESTAMP '2026-04-13 10:33:00 UTC', JSON '{"source":"prometheus"}'),
  ('evt-004',  'user-aha-001', 'invite_sent',          2.0,  TIMESTAMP '2026-04-13 10:48:00 UTC', JSON '{"target":"teammate"}'),
  ('evt-005',  'user-mql-002', 'docs_visit',           1.0,  TIMESTAMP '2026-04-10 14:00:00 UTC', JSON '{"page":"pricing"}'),
  ('evt-006',  'user-attr-003','campaign_clickthrough',1.0,  TIMESTAMP '2026-04-12 16:42:00 UTC', JSON '{"campaign":"q2-launch"}');

-- ---- signals ---------------------------------------------------------------
DELETE FROM `${project}.${dataset}.signals` WHERE id IN ('golden-aha-001', 'golden-mql-002', 'golden-attr-003');

INSERT INTO `${project}.${dataset}.signals`
  (id,                type,                    source,     user_id,         occurred_at,                          payload, metadata)
VALUES
  ('golden-aha-001',  'aha_moment_threshold',  'bigquery', 'user-aha-001',  TIMESTAMP '2026-04-13 10:48:30 UTC',
   JSON '{"threshold":"4_actions_in_first_hour","actions_taken":4,"plan":"free"}',
   JSON '{"trace_hint":"happy-path-demo"}'
  ),
  ('golden-mql-002',  'mql_stale',             'bigquery', 'user-mql-002',  TIMESTAMP '2026-04-12 09:00:00 UTC',
   JSON '{"days_since_last_touch":42,"score":74}',
   JSON '{}'
  ),
  ('golden-attr-003', 'campaign_completed',    'bigquery', 'user-attr-003', TIMESTAMP '2026-04-12 23:59:59 UTC',
   JSON '{"campaign_id":"q2-launch","cohort_size":4123}',
   JSON '{}'
  );
