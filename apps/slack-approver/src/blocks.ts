/**
 * Block Kit card builders for the HITL approval UI.
 *
 * Kept pure (no I/O) so we can snapshot-test every shape the operator sees.
 */
import type { ApprovalRequest, Draft, UserContext } from './types.js';

const MAX_BODY_PREVIEW = 400;

export function approvalCard(record: ApprovalRequest): ReadonlyArray<Record<string, unknown>> {
  const d = record.draft;
  const ctx = record.user_context;
  return [
    {
      type: 'header',
      text: { type: 'plain_text', text: `Lifecycle draft for ${d.audience_segment}` },
    },
    {
      type: 'context',
      elements: [
        { type: 'mrkdwn', text: `*Signal:* \`${record.signal_id}\`` },
        { type: 'mrkdwn', text: `*Channel:* \`${d.channel}\`` },
        ...(d.playbook_slug
          ? [{ type: 'mrkdwn', text: `*Playbook:* \`${d.playbook_slug}\`` }]
          : []),
      ],
    },
    ...userContextBlocks(ctx),
    { type: 'divider' },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*Subject*\n${d.subject}` },
    },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*Body*\n${truncate(d.body_markdown, MAX_BODY_PREVIEW)}` },
    },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*Call to action*\n${d.call_to_action}` },
    },
    {
      type: 'context',
      elements: [{ type: 'mrkdwn', text: `_Rationale: ${d.rationale}_` }],
    },
    { type: 'divider' },
    actionButtons(record),
  ];
}

function userContextBlocks(
  ctx: UserContext | undefined
): ReadonlyArray<Record<string, unknown>> {
  if (!ctx) return [];
  const lines: string[] = [`*user_id:* \`${ctx.user_id}\``];
  if (ctx.plan) lines.push(`*plan:* ${ctx.plan}`);
  if (ctx.lifecycle_stage) lines.push(`*stage:* ${ctx.lifecycle_stage}`);
  if (ctx.company) lines.push(`*company:* ${ctx.company}`);
  if (ctx.recent_event_types?.length) {
    lines.push(
      `*recent activity:* ${ctx.recent_event_types.slice(0, 6).map((e) => `\`${e}\``).join(', ')}`
    );
  }
  return [
    {
      type: 'section',
      text: { type: 'mrkdwn', text: lines.join('\n') },
    },
  ];
}

function actionButtons(record: ApprovalRequest): Record<string, unknown> {
  return {
    type: 'actions',
    block_id: `approval_${record.hitl_id}`,
    elements: [
      {
        type: 'button',
        style: 'primary',
        text: { type: 'plain_text', text: 'Approve' },
        action_id: 'approve_draft',
        value: record.hitl_id,
      },
      {
        type: 'button',
        style: 'danger',
        text: { type: 'plain_text', text: 'Reject' },
        action_id: 'reject_draft',
        value: record.hitl_id,
      },
      {
        type: 'button',
        text: { type: 'plain_text', text: 'Edit' },
        action_id: 'edit_draft',
        value: record.hitl_id,
      },
    ],
  };
}

export function resolvedCard(record: ApprovalRequest): ReadonlyArray<Record<string, unknown>> {
  const d = record.draft;
  return [
    {
      type: 'header',
      text: {
        type: 'plain_text',
        text: `Draft ${record.state.toUpperCase()} — ${d.audience_segment}`,
      },
    },
    {
      type: 'context',
      elements: [
        { type: 'mrkdwn', text: `*Signal:* \`${record.signal_id}\`` },
        { type: 'mrkdwn', text: `*By:* ${record.decided_by ?? 'system'}` },
        { type: 'mrkdwn', text: `*At:* ${record.decided_at ?? '—'}` },
      ],
    },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*Subject*\n${d.subject}` },
    },
  ];
}

export function editModal(record: ApprovalRequest): Record<string, unknown> {
  const d = record.draft;
  return {
    type: 'modal',
    callback_id: 'submit_edit',
    private_metadata: record.hitl_id,
    title: { type: 'plain_text', text: 'Edit draft' },
    submit: { type: 'plain_text', text: 'Save + repost' },
    close: { type: 'plain_text', text: 'Cancel' },
    blocks: [
      {
        type: 'input',
        block_id: 'subject_block',
        label: { type: 'plain_text', text: 'Subject' },
        element: {
          type: 'plain_text_input',
          action_id: 'subject',
          initial_value: d.subject,
          max_length: 140,
        },
      },
      {
        type: 'input',
        block_id: 'body_block',
        label: { type: 'plain_text', text: 'Body (markdown)' },
        element: {
          type: 'plain_text_input',
          action_id: 'body_markdown',
          initial_value: d.body_markdown,
          multiline: true,
          max_length: 4000,
        },
      },
      {
        type: 'input',
        block_id: 'cta_block',
        label: { type: 'plain_text', text: 'Call to action' },
        element: {
          type: 'plain_text_input',
          action_id: 'call_to_action',
          initial_value: d.call_to_action,
          max_length: 80,
        },
      },
    ],
  };
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}

// Re-export so a Python caller can snapshot the empty-state shape in its tests too.
export const EMPTY_DRAFT: Draft = {
  signal_id: '',
  user_id: '',
  audience_segment: '',
  channel: '',
  subject: '',
  body_markdown: '',
  call_to_action: '',
  rationale: '',
  playbook_slug: null,
};
