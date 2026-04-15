---
slug: enterprise-signal-sdr
signal_types:
  - enterprise_signal
  - power_user_signup
audience: account with strong enterprise-intent indicators
channel: SDR handoff + Slack alert to enterprise AE pod
---

## Trigger

A signal fires with an intent score ≥ 80 OR the signup's email domain classifies as Fortune-5000/enterprise. The goal is to reach a human SDR within 30 minutes — speed-to-first-touch dominates win rate at the enterprise end of the funnel.

## Audience cut

Any plan tier, but prioritise signups on work email domains. Exclude consulting-firm and VAR domains from auto-handoff; those need legal review first. Exclude any account already owned by an enterprise AE (duplicate handoff is the single worst outcome here).

## Scoring rubric

`fit_score` ∈ [0,100], `priority` categorical. Weights: intent-data composite 40%, email-domain classification 30%, company size / ARR signal 20%, app-usage signal 10%. Tier-1 fit (≥ 85) should always return `priority="high"`.

## Recommended action

high → Slack alert to the enterprise AE pod channel with lead details + scoring rationale + CRM link, inside 30 minutes. medium → enqueue for tier-2 SDR review within 24h with a scoring breakdown attached. low → put in the inbound-observe segment and revisit weekly.

## Guardrails

Do NOT send outbound email from this workflow — enterprise-tier outreach always comes from an AE on their own domain. Do not reveal intent-data vendor in any external-facing message (contractual). Never include competitor names in the Slack alert even if the intent data contains them.

## Success metric

Speed-to-first-AE-touch (goal: ≤ 30 min for tier-1). Secondary: opp-created rate in 14d.
