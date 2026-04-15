/**
 * Entrypoint. Starts the Bolt + Express app listening on PORT.
 *
 * When SLACK_BOT_TOKEN + SLACK_SIGNING_SECRET are present we wire real Slack
 * interactivity; otherwise we boot HTTP-only so local dev / tests / CI can
 * exercise the approval API without Slack credentials.
 */
import { App as BoltApp, ExpressReceiver } from '@slack/bolt';
import pino from 'pino';

import { buildServer } from './app.js';

const log = pino({ name: 'slack-approver-server' });

const port = Number(process.env.PORT ?? 3030);
const token = process.env.SLACK_BOT_TOKEN;
const signing = process.env.SLACK_SIGNING_SECRET;

let boltApp: BoltApp | null = null;
let boltReceiver: ExpressReceiver | null = null;
if (token && signing) {
  boltReceiver = new ExpressReceiver({ signingSecret: signing, endpoints: '/slack/events' });
  boltApp = new BoltApp({ token, receiver: boltReceiver });
  log.info('bolt.enabled');
} else {
  log.warn(
    {
      reason:
        'SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET not set — HTTP API is live, Slack interactivity is stubbed out.',
    },
    'bolt.disabled'
  );
}

const bundle = buildServer({ boltApp, boltReceiver });

bundle.express.listen(port, () => {
  log.info({ port }, 'slack-approver listening');
});
