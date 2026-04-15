---
slug: conversion-attribution-report
signal_types:
  - conversion_milestone
audience: RevOps + marketing leadership
channel: Slack report to #revops + CRM enrichment
---

## Trigger

An account transitioned from free/trial to a paid plan for the first time. We want a first-touch + multi-touch attribution breakdown inside an hour so marketing can correctly credit the campaigns that actually drove the conversion.

## Analysis rubric

Return the `first_touch` campaign, the `last_touch` campaign, and a `multi_touch` weighted list (each entry: campaign_id, channel, weight 0–1 summing to 1.0). Call out the single strongest driver in `top_driver_rationale` — one sentence naming the specific touch and the evidence from BQ. Confidence categorical: high | medium | low based on how much of the journey is captured.

## Data sources

BigQuery `marketing_touches` table keyed on `user_id` + `touch_at`. Join against `campaigns` for display names. If a touch is missing its campaign metadata, label the weight entry as `"unattributed"` rather than dropping it — under-attributed revenue is worse than mislabelled revenue for monthly board reporting.

## Recommended action

Post a structured report to `#revops` Slack: conversion summary, top driver, weighted table, confidence, plus the full journey as a collapsed section. Enrich the account record with `first_touch_campaign_id` and `multi_touch_json` so Salesforce reports inherit the attribution.

## Guardrails

Never expose individual user_id values in the public report — aggregate by cohort when discussing patterns. If confidence is low, explicitly state the gaps (missing UTM, first-party-cookie loss, etc) rather than producing a confident-sounding report on thin data. Do not rerun attribution for the same `signal_id` — the write is idempotent on `signal_id + campaign_id`.

## Success metric

Time-from-conversion-to-report ≤ 1h. Secondary: analyst override rate < 10% (i.e. humans rarely overrule our weights).
