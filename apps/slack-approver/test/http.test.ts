import { describe, expect, it } from 'vitest';
import type { Express } from 'express';
import http from 'node:http';
import { AddressInfo } from 'node:net';

import { buildServer } from '../src/app.js';
import type { CreateApprovalBody, Draft } from '../src/types.js';

const DRAFT: Draft = {
  signal_id: 'sig-1',
  user_id: 'u1',
  audience_segment: 'x',
  channel: 'email',
  subject: 's',
  body_markdown: 'b',
  call_to_action: 'c',
  rationale: 'r',
  playbook_slug: null,
};

function startExpress(app: Express): Promise<{ url: string; close: () => void }> {
  return new Promise((resolve) => {
    const srv = http.createServer(app).listen(0, () => {
      const { port } = srv.address() as AddressInfo;
      resolve({
        url: `http://127.0.0.1:${port}`,
        close: () => srv.close(),
      });
    });
  });
}

async function json(u: string, opts: RequestInit = {}): Promise<{ status: number; body: any }> {
  const r = await fetch(u, {
    headers: { 'content-type': 'application/json', ...(opts.headers ?? {}) },
    ...opts,
  });
  const body = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text();
  return { status: r.status, body };
}

describe('HTTP surface', () => {
  it('create → get → approve flow round-trips through the store', async () => {
    const bundle = buildServer({ defaultTimeoutMs: 60_000 });
    const srv = await startExpress(bundle.express);
    try {
      const body: CreateApprovalBody = { signal_id: 'sig-1', channel_id: 'C1', draft: DRAFT };
      const created = await json(`${srv.url}/approvals`, { method: 'POST', body: JSON.stringify(body) });
      expect(created.status).toBe(201);
      expect(created.body.state).toBe('posted');
      const hitl_id = created.body.hitl_id;

      const fetched = await json(`${srv.url}/approvals/${hitl_id}`);
      expect(fetched.body.state).toBe('posted');

      // Simulate the Slack-side approval by transitioning directly in the store.
      bundle.store.transition(hitl_id, 'approved', { by: 'test-user' });

      const after = await json(`${srv.url}/approvals/${hitl_id}`);
      expect(after.body.state).toBe('approved');
      expect(after.body.decided_by).toBe('test-user');
    } finally {
      bundle.stop();
      srv.close();
    }
  });

  it('/wait returns immediately on terminal state', async () => {
    const bundle = buildServer();
    const srv = await startExpress(bundle.express);
    try {
      const created = await json(`${srv.url}/approvals`, {
        method: 'POST',
        body: JSON.stringify({ signal_id: 'sig-2', channel_id: 'C', draft: DRAFT }),
      });
      const hitl_id = created.body.hitl_id;
      bundle.store.transition(hitl_id, 'rejected', { by: 'u' });

      const r = await json(`${srv.url}/approvals/${hitl_id}/wait?timeout_ms=5000`);
      expect(r.status).toBe(200);
      expect(r.body.state).toBe('rejected');
    } finally {
      bundle.stop();
      srv.close();
    }
  });

  it('/wait polls until state turns terminal', async () => {
    const bundle = buildServer();
    const srv = await startExpress(bundle.express);
    try {
      const created = await json(`${srv.url}/approvals`, {
        method: 'POST',
        body: JSON.stringify({ signal_id: 'sig-3', channel_id: 'C', draft: DRAFT }),
      });
      const hitl_id = created.body.hitl_id;
      setTimeout(() => {
        bundle.store.transition(hitl_id, 'approved', { by: 'delayed' });
      }, 100);

      const r = await json(`${srv.url}/approvals/${hitl_id}/wait?timeout_ms=5000&poll_ms=50`);
      expect(r.status).toBe(200);
      expect(r.body.state).toBe('approved');
      expect(r.body.decided_by).toBe('delayed');
    } finally {
      bundle.stop();
      srv.close();
    }
  });

  it('POST /approvals rejects missing fields', async () => {
    const bundle = buildServer();
    const srv = await startExpress(bundle.express);
    try {
      const r = await json(`${srv.url}/approvals`, {
        method: 'POST',
        body: JSON.stringify({ signal_id: 'x' }),
      });
      expect(r.status).toBe(400);
    } finally {
      bundle.stop();
      srv.close();
    }
  });

  it('/executed only allowed after /approved', async () => {
    const bundle = buildServer();
    const srv = await startExpress(bundle.express);
    try {
      const created = await json(`${srv.url}/approvals`, {
        method: 'POST',
        body: JSON.stringify({ signal_id: 'sig-4', channel_id: 'C', draft: DRAFT }),
      });
      const hitl_id = created.body.hitl_id;
      const tooEarly = await json(`${srv.url}/approvals/${hitl_id}/executed`, { method: 'POST', body: '{}' });
      expect(tooEarly.status).toBe(409);

      bundle.store.transition(hitl_id, 'approved', { by: 'test' });
      const ok = await json(`${srv.url}/approvals/${hitl_id}/executed`, { method: 'POST', body: '{}' });
      expect(ok.status).toBe(200);
      expect(ok.body.state).toBe('executed');
    } finally {
      bundle.stop();
      srv.close();
    }
  });
});
