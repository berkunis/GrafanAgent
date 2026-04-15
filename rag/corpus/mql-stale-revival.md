---
slug: mql-stale-revival
signal_types:
  - mql_stale
audience: MQL with 30+ days since last touch, score ≥ 60
channel: SDR reassignment + personalised outbound email
---

## Trigger

A marketing-qualified lead (MQL) has gone untouched for 30+ consecutive days AND still carries a lead score ≥ 60. Staleness plus latent fit is the actionable combination — older than 30d with a low score goes to the nurture drip, not SDR.

## Audience cut

Plan: any (includes free users who signed up via content). Days since last meaningful SDR/CSM touch: ≥ 30. Current lead score: ≥ 60. Not currently in a paying-customer parent account. Not opted out of outbound. Not flagged "do not contact" in the CRM.

## Scoring rubric

Produce a numeric `fit_score` in [0,100] and a categorical `priority` (high | medium | low). Weight the inputs as follows: intent-data score 35%, email-domain classification 25%, recent app engagement in BQ 20%, title/seniority signal 15%, account firmographics 5%. Name the three strongest individual drivers in plain English.

## Recommended action

high → same-day SDR handoff with the scoring rationale posted to the owning SDR's Slack DM. medium → queued for next-day tier-2 sequence + CRM note. low → downgrade to nurture, do not ping a human.

## Guardrails

Never reassign an MQL that is currently in an active open opportunity. Do not include raw email addresses in the Slack message — reference the lead by `lead_id` and the company name only. Skip entirely if any `do_not_contact=true` flag is present.

## Success metric

SDR reply rate within 48 hours of handoff. Secondary: meetings booked within 14 days.
