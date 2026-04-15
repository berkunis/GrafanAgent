---
slug: usage-drop-paid
signal_types:
  - usage_drop
audience: paying team or enterprise account whose usage has collapsed
channel: Slack alert to CSM + email
---

## Trigger

A paying account's 7-day active-user count has fallen by 60% or more compared to its trailing 4-week average. This is a lagging indicator of churn risk — the goal is to surface it to a human before the renewal conversation.

## Audience cut

Plan: team or enterprise. Tenure: ≥ 90 days (otherwise the baseline is too noisy). 7-day WAU ÷ 28-day WAU ≤ 0.4. Exclude accounts where the CSM has marked a known migration or holiday in the notes field.

## Message angle

This is primarily an internal workflow. The Slack alert to the CSM includes the account name, the usage chart link, the top three features that dropped, and any open support tickets. The outbound customer email (CSM-sent, not automated) is a short "haven't heard from you in a while — want to hop on a call?" note that references the specific team members who went dark.

## Guardrails

Do not trigger during the first 14 days of a known onboarding pause. Never share the raw usage chart externally. Always give the CSM a 24-hour window to claim the alert before any automated email fires.

## Success metric

Time-to-first-CSM-action after alert. Secondary: usage recovery within 30 days of intervention.
