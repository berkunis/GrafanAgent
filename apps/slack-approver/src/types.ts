/**
 * Shared types across the Slack approval app.
 *
 * `Draft` mirrors the Python `CampaignDraft` schema exactly — it's the payload
 * the lifecycle agent posts to us; we round-trip it back to the Python side on
 * approval so the draft shape is defined once.
 */

export type ApprovalState =
  | 'draft'
  | 'posted'
  | 'approved'
  | 'rejected'
  | 'edited'
  | 'timed_out'
  | 'executed'
  | 'cancelled';

export const TERMINAL_STATES: ReadonlyArray<ApprovalState> = [
  'approved',
  'rejected',
  'timed_out',
  'executed',
  'cancelled',
];

export interface Draft {
  signal_id: string;
  user_id: string;
  audience_segment: string;
  channel: string;
  subject: string;
  body_markdown: string;
  call_to_action: string;
  rationale: string;
  playbook_slug: string | null;
}

export interface UserContext {
  user_id: string;
  plan?: string;
  lifecycle_stage?: string;
  company?: string;
  recent_event_types?: string[];
}

export interface ApprovalRequest {
  hitl_id: string;
  signal_id: string;
  channel_id: string;
  draft: Draft;
  user_context?: UserContext;
  created_at: string;
  state: ApprovalState;
  history: ApprovalTransition[];
  message_ts?: string;
  decided_at?: string;
  decided_by?: string;
}

export interface ApprovalTransition {
  from: ApprovalState;
  to: ApprovalState;
  at: string;
  by?: string;
  reason?: string;
}

export interface CreateApprovalBody {
  signal_id: string;
  channel_id: string;
  draft: Draft;
  user_context?: UserContext;
  timeout_s?: number;
}

export interface EditedFields {
  subject: string;
  body_markdown: string;
  call_to_action: string;
}
