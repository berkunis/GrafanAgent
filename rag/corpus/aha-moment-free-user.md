---
slug: aha-moment-free-user
signal_types:
  - aha_moment_threshold
audience: free-plan user who hit first-hour activation
channel: email + in-product
---

## Trigger

A free-plan user completes at least four distinct meaningful actions within the first hour of signup (e.g. create dashboard, configure alert, add integration, invite teammate). The intent is to reach them while their momentum is still fresh, typically within 15–45 minutes of the trigger firing.

## Audience cut

Plan: free. Sign-up age: < 24 hours. At least four activation events on distinct features. Exclude anyone who has already been contacted today via lifecycle email.

## Message angle

Lead with recognition of what they just did by name ("You just wired up X, Y, and Z — that's the same pattern our best teams use"). Offer one specific next step that unlocks outsized value: share the dashboard with a teammate, connect a second data source, or configure a smarter alert. Avoid pitching paid plans in this touch; the goal is depth, not conversion.

## Guardrails

Skip if the user signed up through a managed-demo channel, if their email domain is on the internal exclusion list, or if they have opted out of product emails. Never trigger for users with a pending support ticket. If the user's dashboards reference production data, do not mention the specific dashboard name — use a generic placeholder.

## Success metric

Second-day retention (active on day 2 after signup) and inviter conversion (did they send at least one teammate invite in the next 48h).
