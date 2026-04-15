---
slug: reengagement-dormant-90d
signal_types:
  - usage_drop
audience: any account with 90+ days of no activity
channel: email
---

## Trigger

An account has had no sessions in 90 consecutive days. Unlike the acute usage-drop signal, this is a long-tail re-engagement list and the bar for contacting is high.

## Audience cut

Plan: any. Days since last session: ≥ 90. Days since last outbound marketing email: ≥ 60 (otherwise we hammer dormant accounts). Opt-in status: explicitly opted in (not merely "never unsubscribed").

## Message angle

A low-pressure "we shipped these things since you were last here" email. Pick the 3–5 concrete changes most relevant to their original use case. No urgency, no "we miss you", no countdown. Offer one one-click path to restart — ideally importing one of their old dashboards from backup.

## Guardrails

Suppress any account that has filed a security or compliance request in the last 12 months. Never include competitor references. Cap the global daily volume of this campaign at 0.5% of the opted-in base.

## Success metric

Reactivation session within 30 days. Secondary: unsubscribe rate (must stay below 0.6% of sends).
