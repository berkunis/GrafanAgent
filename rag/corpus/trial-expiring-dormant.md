---
slug: trial-expiring-dormant
signal_types:
  - trial_expiring
audience: trial user who has gone dark; trial ends in < 7 days
channel: email
---

## Trigger

A trial user is 7 or fewer days from trial end AND has had no active session in the last 10 days. Goal is re-engagement, not hard-selling a plan they may not be ready for.

## Audience cut

Plan: trial. Days until trial end: ≤ 7. Days since last session: ≥ 10. Excludes: accounts where the primary user marked "paused evaluation" in the feedback survey; accounts with open Zendesk tickets in `on_hold` state.

## Message angle

Low-pressure check-in. Acknowledge they were busy, share one 90-second video of the single most valuable workflow for their stated use case, and offer a trial extension if they want another two weeks with a live pair-up. Avoid countdown timers and "your trial is ending!" urgency — it reads as panic.

## Guardrails

Do not send multiple re-engagement messages in the same week. If the user has already received a dormant-trial nudge in the previous 21 days, skip. Do not attach files larger than 200 KB.

## Success metric

Session within 7 days of send. Secondary: trial-extension requests per 100 sends.
