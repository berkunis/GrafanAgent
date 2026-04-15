/**
 * Approval state machine + in-memory store.
 *
 * Every transition is validated against ALLOWED_TRANSITIONS; disallowed moves
 * throw so a buggy caller can never push state into a shape the dashboard
 * doesn't understand. The store is in-process for simplicity; a restart loses
 * pending approvals. For production swap for SQLite or Cloud SQL — the Store
 * interface is intentionally narrow.
 */
import { randomUUID } from 'node:crypto';

import {
  TERMINAL_STATES,
  type ApprovalRequest,
  type ApprovalState,
  type ApprovalTransition,
  type CreateApprovalBody,
  type Draft,
  type EditedFields,
} from './types.js';

const ALLOWED_TRANSITIONS: Readonly<Record<ApprovalState, ReadonlyArray<ApprovalState>>> = {
  draft:     ['posted', 'cancelled'],
  posted:    ['approved', 'rejected', 'edited', 'timed_out', 'cancelled'],
  edited:    ['posted', 'cancelled'],          // re-approval after edit
  approved:  ['executed', 'cancelled'],
  rejected:  [],
  timed_out: [],
  executed:  [],
  cancelled: [],
};

export class InvalidTransitionError extends Error {
  constructor(from: ApprovalState, to: ApprovalState) {
    super(`invalid approval state transition: ${from} → ${to}`);
    this.name = 'InvalidTransitionError';
  }
}

export class ApprovalStore {
  private readonly byId = new Map<string, ApprovalRequest>();

  list(): ApprovalRequest[] {
    return Array.from(this.byId.values());
  }

  get(id: string): ApprovalRequest | undefined {
    return this.byId.get(id);
  }

  create(body: CreateApprovalBody): ApprovalRequest {
    const hitl_id = `hitl_${randomUUID()}`;
    const record: ApprovalRequest = {
      hitl_id,
      signal_id: body.signal_id,
      channel_id: body.channel_id,
      draft: body.draft,
      user_context: body.user_context,
      created_at: new Date().toISOString(),
      state: 'draft',
      history: [],
    };
    this.byId.set(hitl_id, record);
    return record;
  }

  transition(id: string, to: ApprovalState, opts: { by?: string; reason?: string } = {}): ApprovalRequest {
    const record = this.mustGet(id);
    const from = record.state;
    if (!ALLOWED_TRANSITIONS[from].includes(to)) {
      throw new InvalidTransitionError(from, to);
    }
    const at = new Date().toISOString();
    const transition: ApprovalTransition = { from, to, at, ...opts };
    record.state = to;
    record.history.push(transition);
    if (to === 'approved' || to === 'rejected' || to === 'timed_out') {
      record.decided_at = at;
      record.decided_by = opts.by;
    }
    return record;
  }

  setMessageTs(id: string, ts: string): void {
    const record = this.mustGet(id);
    record.message_ts = ts;
  }

  applyEdit(id: string, edits: EditedFields, editor?: string): ApprovalRequest {
    const record = this.mustGet(id);
    const newDraft: Draft = {
      ...record.draft,
      subject: edits.subject,
      body_markdown: edits.body_markdown,
      call_to_action: edits.call_to_action,
    };
    record.draft = newDraft;
    this.transition(id, 'edited', { by: editor, reason: 'operator edit' });
    this.transition(id, 'posted', { by: editor, reason: 'edit applied — re-awaiting approval' });
    return record;
  }

  private mustGet(id: string): ApprovalRequest {
    const record = this.byId.get(id);
    if (!record) {
      throw new Error(`approval not found: ${id}`);
    }
    return record;
  }
}

export function isTerminal(state: ApprovalState): boolean {
  // Terminal from a waiter's POV as soon as a decision has been made. `approved`
  // still has `executed` / `cancelled` follow-ups, but the waiter can return
  // and the caller drives the next transition explicitly.
  return TERMINAL_STATES.includes(state);
}

/**
 * Scan the store for approvals past their posted TTL and move them to
 * `timed_out`. Called on an interval by the server. Returns the number of
 * approvals timed out on this tick.
 */
export function expireOverdue(
  store: ApprovalStore,
  ttl_ms: number,
  now: Date = new Date()
): number {
  let expired = 0;
  for (const record of store.list()) {
    if (record.state !== 'posted') continue;
    const posted = record.history.find((h) => h.to === 'posted');
    if (!posted) continue;
    const postedAt = new Date(posted.at).getTime();
    if (now.getTime() - postedAt >= ttl_ms) {
      store.transition(record.hitl_id, 'timed_out', { reason: `no action within ${ttl_ms}ms` });
      expired += 1;
    }
  }
  return expired;
}
