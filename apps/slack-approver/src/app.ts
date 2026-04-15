/**
 * HTTP + Slack surface for the approval app.
 *
 * HTTP routes (called by the Python Slack MCP):
 *   POST   /approvals                 create a new approval, post the card, return hitl_id
 *   GET    /approvals/:id             read current state + draft
 *   GET    /approvals/:id/wait        long-poll until terminal state
 *   POST   /approvals/:id/cancel      cancel an in-flight approval
 *   POST   /approvals/:id/executed    mark as executed after the downstream action runs
 *   GET    /healthz
 *
 * Slack interactivity is registered on the Bolt app (`wireSlack`):
 *   approve_draft button   → state → approved, update message, resolve waiters
 *   reject_draft button    → state → rejected, update message, resolve waiters
 *   edit_draft button      → open edit modal
 *   submit_edit view submit→ applyEdit() + repost card
 */
import { App as BoltApp, ExpressReceiver } from '@slack/bolt';
import type { WebClient } from '@slack/web-api';
import type { Express, Request, Response } from 'express';
import express from 'express';
import pino from 'pino';

import { approvalCard, editModal, resolvedCard } from './blocks.js';
import {
  ApprovalStore,
  InvalidTransitionError,
  expireOverdue,
  isTerminal,
} from './state.js';
import type { ApprovalRequest, ApprovalState, CreateApprovalBody } from './types.js';

const log = pino({ name: 'slack-approver', level: process.env.LOG_LEVEL ?? 'info' });

interface Options {
  store?: ApprovalStore;
  // When unset, Slack posting / responding is skipped and the HTTP surface
  // still works — useful for tests and local dev without a real Slack token.
  slackClient?: WebClient | null;
  // When set, `approve_draft` / `reject_draft` / `edit_draft` handlers are
  // wired on the Bolt app. `boltReceiver` must be supplied alongside so the
  // Express surface can mount `/slack/events`.
  boltApp?: BoltApp | null;
  boltReceiver?: ExpressReceiver | null;
  defaultTimeoutMs?: number;
}

export interface ServerBundle {
  express: Express;
  store: ApprovalStore;
  boltApp?: BoltApp | null;
  stop(): void;
}

export function buildServer(opts: Options = {}): ServerBundle {
  const store = opts.store ?? new ApprovalStore();
  const defaultTimeoutMs = opts.defaultTimeoutMs ?? 5 * 60 * 1000;
  const slack = opts.slackClient ?? null;

  const app = express();
  app.use(express.json({ limit: '1mb' }));
  if (opts.boltReceiver) {
    app.use(opts.boltReceiver.router);
  }

  app.get('/healthz', (_req: Request, res: Response) => {
    res.json({ status: 'ok', service: 'slack-approver', open_approvals: store.list().length });
  });

  app.post('/approvals', asyncRoute(async (req, res) => {
    const body = req.body as CreateApprovalBody;
    if (!body?.draft || !body.channel_id || !body.signal_id) {
      res.status(400).json({ error: 'signal_id, channel_id, and draft are required' });
      return;
    }
    const record = store.create(body);
    store.transition(record.hitl_id, 'posted', { reason: 'created and posted' });

    if (slack) {
      try {
        const posted = await slack.chat.postMessage({
          channel: body.channel_id,
          blocks: approvalCard(record) as any,
          text: `Lifecycle draft awaiting approval — signal ${body.signal_id}`,
        });
        if (posted.ts) store.setMessageTs(record.hitl_id, posted.ts);
      } catch (err) {
        log.error({ err, hitl_id: record.hitl_id }, 'slack.postMessage failed');
      }
    }

    res.status(201).json(store.get(record.hitl_id));
  }));

  app.get('/approvals/:id', asyncRoute(async (req, res) => {
    const record = store.get(req.params.id);
    if (!record) return res.status(404).json({ error: 'not found' });
    res.json(record);
  }));

  app.get('/approvals/:id/wait', asyncRoute(async (req, res) => {
    const id = req.params.id;
    const timeoutMs = Math.min(
      Number(req.query.timeout_ms ?? defaultTimeoutMs),
      10 * 60 * 1000
    );
    const pollMs = Number(req.query.poll_ms ?? 250);
    const end = Date.now() + timeoutMs;

    while (Date.now() < end) {
      const record = store.get(id);
      if (!record) return res.status(404).json({ error: 'not found' });
      if (isTerminal(record.state)) return res.json(record);
      await sleep(pollMs);
    }
    // Timed out on server side — not the same as approval `timed_out`; caller
    // can re-poll or decide to cancel.
    res.status(408).json({ error: 'wait timed out', ...(store.get(id) ?? {}) });
  }));

  app.post('/approvals/:id/cancel', asyncRoute(async (req, res) => {
    try {
      const record = store.transition(req.params.id, 'cancelled', {
        reason: (req.body?.reason as string) ?? 'cancelled by caller',
      });
      res.json(record);
    } catch (err) {
      res.status(err instanceof InvalidTransitionError ? 409 : 500).json({ error: String(err) });
    }
  }));

  app.post('/approvals/:id/executed', asyncRoute(async (req, res) => {
    try {
      const record = store.transition(req.params.id, 'executed', {
        by: (req.body?.by as string) ?? 'agent',
        reason: (req.body?.reason as string) ?? 'downstream action completed',
      });
      res.json(record);
    } catch (err) {
      res.status(err instanceof InvalidTransitionError ? 409 : 500).json({ error: String(err) });
    }
  }));

  // TTL reaper — moves posted approvals to `timed_out` after their TTL.
  const reaper = setInterval(() => {
    const n = expireOverdue(store, defaultTimeoutMs);
    if (n) log.info({ expired: n }, 'expired.overdue');
  }, 10_000);
  reaper.unref?.();

  if (opts.boltApp) {
    wireSlack(opts.boltApp, store, log);
  }

  return {
    express: app,
    store,
    boltApp: opts.boltApp ?? null,
    stop() {
      clearInterval(reaper);
    },
  };
}

function wireSlack(boltApp: BoltApp, store: ApprovalStore, logger: pino.Logger): void {
  boltApp.action('approve_draft', async ({ ack, action, body, client }) => {
    await ack();
    const hitl_id = (action as any).value as string;
    const by = (body as any).user?.username ?? (body as any).user?.id ?? 'unknown';
    try {
      const record = store.transition(hitl_id, 'approved', { by });
      await updateSlackMessage(client, record);
    } catch (err) {
      logger.error({ err, hitl_id }, 'approve action failed');
    }
  });

  boltApp.action('reject_draft', async ({ ack, action, body, client }) => {
    await ack();
    const hitl_id = (action as any).value as string;
    const by = (body as any).user?.username ?? (body as any).user?.id ?? 'unknown';
    try {
      const record = store.transition(hitl_id, 'rejected', { by, reason: 'rejected in Slack' });
      await updateSlackMessage(client, record);
    } catch (err) {
      logger.error({ err, hitl_id }, 'reject action failed');
    }
  });

  boltApp.action('edit_draft', async ({ ack, action, body, client }) => {
    await ack();
    const hitl_id = (action as any).value as string;
    const record = store.get(hitl_id);
    if (!record) return;
    try {
      await client.views.open({
        trigger_id: (body as any).trigger_id,
        view: editModal(record) as any,
      });
    } catch (err) {
      logger.error({ err, hitl_id }, 'edit modal open failed');
    }
  });

  boltApp.view('submit_edit', async ({ ack, view, body, client }) => {
    await ack();
    const hitl_id = view.private_metadata;
    const values = view.state.values as Record<string, Record<string, { value?: string }>>;
    const edits = {
      subject: values.subject_block?.subject?.value ?? '',
      body_markdown: values.body_block?.body_markdown?.value ?? '',
      call_to_action: values.cta_block?.call_to_action?.value ?? '',
    };
    const editor = (body as any).user?.username ?? (body as any).user?.id ?? 'unknown';
    try {
      const record = store.applyEdit(hitl_id, edits, editor);
      await updateSlackMessage(client, record);
    } catch (err) {
      logger.error({ err, hitl_id }, 'edit submit failed');
    }
  });
}

async function updateSlackMessage(client: WebClient, record: ApprovalRequest): Promise<void> {
  if (!record.message_ts) return;
  const blocks =
    record.state === 'posted' ? approvalCard(record) : resolvedCard(record);
  try {
    await client.chat.update({
      channel: record.channel_id,
      ts: record.message_ts,
      blocks: blocks as any,
      text: `${record.state} — ${record.draft.audience_segment}`,
    });
  } catch (err) {
    // Non-fatal — the state machine already reflects the truth.
  }
}

function asyncRoute(
  handler: (req: Request, res: Response) => Promise<unknown>
) {
  return (req: Request, res: Response) => {
    handler(req, res).catch((err) => {
      if (!res.headersSent) {
        res.status(500).json({ error: String(err) });
      }
    });
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type { ApprovalRequest, ApprovalState };
