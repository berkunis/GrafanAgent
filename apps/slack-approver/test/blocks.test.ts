import { describe, expect, it } from 'vitest';

import { approvalCard, editModal, resolvedCard } from '../src/blocks.js';
import { ApprovalStore } from '../src/state.js';
import type { Draft } from '../src/types.js';

const DRAFT: Draft = {
  signal_id: 'golden-aha-001',
  user_id: 'user-aha-001',
  audience_segment: 'free_activated_today',
  channel: 'email',
  subject: 'You just wired the exact pattern our best teams use',
  body_markdown: 'x'.repeat(2000),
  call_to_action: 'Share your dashboard',
  rationale: 'aha-moment + invite momentum',
  playbook_slug: 'aha-moment-free-user',
};

function makeRecord() {
  const s = new ApprovalStore();
  const r = s.create({
    signal_id: DRAFT.signal_id,
    channel_id: 'C123',
    draft: DRAFT,
    user_context: {
      user_id: 'user-aha-001',
      plan: 'free',
      lifecycle_stage: 'activated',
      company: 'Lattice Loop',
      recent_event_types: ['dashboard_created', 'alert_configured', 'invite_sent'],
    },
  });
  s.transition(r.hitl_id, 'posted');
  return s.get(r.hitl_id)!;
}

describe('Block Kit builders', () => {
  it('approvalCard includes the three action buttons with the hitl_id as value', () => {
    const blocks = approvalCard(makeRecord()) as any[];
    const actions = blocks.find((b) => b.type === 'actions');
    const ids = actions.elements.map((e: any) => e.action_id);
    expect(ids).toEqual(['approve_draft', 'reject_draft', 'edit_draft']);
    for (const el of actions.elements) {
      expect(el.value).toMatch(/^hitl_/);
    }
  });

  it('approvalCard truncates long bodies', () => {
    const blocks = approvalCard(makeRecord()) as any[];
    const bodyBlock = blocks.find((b: any) => b.text?.text?.startsWith('*Body*'));
    expect(bodyBlock.text.text).toContain('…');
    expect(bodyBlock.text.text.length).toBeLessThan(500);
  });

  it('approvalCard surfaces user context', () => {
    const blocks = approvalCard(makeRecord()) as any[];
    const flat = JSON.stringify(blocks);
    expect(flat).toContain('Lattice Loop');
    expect(flat).toContain('dashboard_created');
    expect(flat).toContain('free');
  });

  it('resolvedCard reflects the terminal state', () => {
    const record = makeRecord();
    record.state = 'approved';
    record.decided_by = 'isil';
    record.decided_at = '2026-04-15T00:00:00Z';
    const blocks = resolvedCard(record) as any[];
    expect((blocks[0] as any).text.text).toContain('APPROVED');
    expect(JSON.stringify(blocks)).toContain('isil');
  });

  it('editModal preloads current draft values', () => {
    const modal = editModal(makeRecord()) as any;
    expect(modal.callback_id).toBe('submit_edit');
    expect(modal.private_metadata).toMatch(/^hitl_/);
    const flat = JSON.stringify(modal);
    expect(flat).toContain(DRAFT.subject);
    expect(flat).toContain(DRAFT.call_to_action);
  });
});
