import { describe, expect, it } from 'vitest';

import {
  ApprovalStore,
  InvalidTransitionError,
  expireOverdue,
  isTerminal,
} from '../src/state.js';
import type { CreateApprovalBody, Draft } from '../src/types.js';

const DRAFT: Draft = {
  signal_id: 'sig-1',
  user_id: 'u1',
  audience_segment: 'free_activated_today',
  channel: 'email',
  subject: 'Hi',
  body_markdown: 'body',
  call_to_action: 'CTA',
  rationale: 'test',
  playbook_slug: 'aha-moment-free-user',
};

const BODY: CreateApprovalBody = {
  signal_id: DRAFT.signal_id,
  channel_id: 'C123',
  draft: DRAFT,
};

describe('state machine', () => {
  it('creates a draft in the draft state', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    expect(r.state).toBe('draft');
    expect(r.hitl_id).toMatch(/^hitl_/);
    expect(r.history).toHaveLength(0);
  });

  it('draft → posted → approved records history and decided fields', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    s.transition(r.hitl_id, 'posted');
    const final = s.transition(r.hitl_id, 'approved', { by: 'isil' });
    expect(final.state).toBe('approved');
    expect(final.decided_by).toBe('isil');
    expect(final.decided_at).toBeDefined();
    expect(final.history.map((h) => `${h.from}→${h.to}`)).toEqual([
      'draft→posted',
      'posted→approved',
    ]);
  });

  it('rejects invalid transitions', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    expect(() => s.transition(r.hitl_id, 'executed')).toThrow(InvalidTransitionError);
  });

  it('cannot transition out of a terminal state', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    s.transition(r.hitl_id, 'posted');
    s.transition(r.hitl_id, 'rejected');
    expect(() => s.transition(r.hitl_id, 'posted')).toThrow(InvalidTransitionError);
    expect(isTerminal('rejected')).toBe(true);
  });

  it('applyEdit loops through edited → posted with new content', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    s.transition(r.hitl_id, 'posted');
    const edited = s.applyEdit(
      r.hitl_id,
      {
        subject: 'New subject',
        body_markdown: 'New body',
        call_to_action: 'New CTA',
      },
      'ryan'
    );
    expect(edited.state).toBe('posted');
    expect(edited.draft.subject).toBe('New subject');
    expect(edited.draft.body_markdown).toBe('New body');
    const tail = edited.history.slice(-2).map((h) => `${h.from}→${h.to}`);
    expect(tail).toEqual(['posted→edited', 'edited→posted']);
  });

  it('expireOverdue moves stale posted approvals to timed_out', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    s.transition(r.hitl_id, 'posted');
    const future = new Date(Date.now() + 60_000);
    const n = expireOverdue(s, 1_000, future);
    expect(n).toBe(1);
    expect(s.get(r.hitl_id)?.state).toBe('timed_out');
  });

  it('expireOverdue ignores already-decided approvals', () => {
    const s = new ApprovalStore();
    const r = s.create(BODY);
    s.transition(r.hitl_id, 'posted');
    s.transition(r.hitl_id, 'approved');
    expect(expireOverdue(s, 1, new Date(Date.now() + 60_000))).toBe(0);
  });
});
