---
slug: trial-expiring-engaged
signal_types:
  - trial_expiring
audience: trial user with healthy engagement, trial ends in < 7 days
channel: email + Slack handoff to AE
---

## Trigger

A trial user has 7 or fewer days remaining on their trial AND has above-median engagement (weekly active, at least two teammates invited, dashboards saved). They are a real conversion candidate and need a human touch, not a scripted nudge.

## Audience cut

Plan: trial. Days until trial end: ≤ 7. Weekly active users on the account: ≥ 2. Saved dashboards: ≥ 3. Exclude accounts owned by an AE who has already logged an outreach in the CRM within the last 5 days.

## Message angle

Two-sentence email from the assigned AE (not marketing). Name the specific wins we've seen on their workspace — invited teammates, dashboards they built, integrations wired — and offer a 20-minute call to map their rollout. Follow up 48 hours later with a calendar link if no reply.

## Guardrails

Do not send from a generic `no-reply@` address. Do not reference specific customer data values — reference feature usage instead. Always route through the AE's outbox so replies land with a human.

## Success metric

Trial-to-paid conversion within 14 days of trigger. Secondary: reply rate on the outbound message.
