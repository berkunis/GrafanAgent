---
slug: campaign-performance-debrief
signal_types:
  - campaign_completed
  - channel_attribution_q
audience: campaign owner + demand-gen lead
channel: Slack thread in #demand-gen + a linked doc
---

## Trigger

A campaign finished its configured run OR a RevOps user asked an ad-hoc channel/campaign question. The output is a compact debrief that lets humans make a stop/continue/scale call on the same campaign for next quarter.

## Analysis rubric

Return: campaign summary (id, channel, cohort size, cost if available), `kpi` table (opens / clicks / conversions / pipeline-generated / closed-won), `first_touch_share` and `multi_touch_share` percentages, a `three_line_verdict` (what worked, what didn't, what to change), and a boolean `recommend_rerun`. Confidence categorical as in conversion-attribution.

## Data sources

BigQuery `campaigns`, `campaign_touches`, and `opportunities` tables. For ad-hoc questions without a specific campaign_id, allow the user to filter by channel + date range and aggregate at the channel level.

## Recommended action

Post the debrief to `#demand-gen`. Mention the campaign owner by handle. If `recommend_rerun=false`, surface the top two reasons explicitly so the owner can contest. Always link back to the raw BQ query that generated the verdict — transparency beats polish on internal reports.

## Guardrails

Do not propose creative changes — this is an analytics report, not a copywriting doc. Never compare performance to a competitor's campaign even if external data is available. If cohort size < 100, mark confidence=low and recommend "too small to call" rather than producing a strong verdict.

## Success metric

Time-to-debrief after campaign end ≤ 4h. Secondary: owner acts on the `recommend_rerun` call within 7 days.
