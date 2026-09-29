// Observational OpenCode adapter. Copy to ~/.config/opencode/plugins/ and set the reporter path.
// OpenCode V2 loads the default export's setup(); V1 loads CanopyPlugin or server().
// Reports lifecycle state only. Never approves a permission, blocks a tool, or rewrites a prompt.
import { spawn } from 'node:child_process';

const reporter = '/absolute/path/to/tmux-canopy/scripts/agent-hook';
const types = new Set([
  'session.created', 'session.deleted', 'session.status', 'session.idle', 'session.error',
  'permission.asked', 'permission.replied', 'permission.v2.asked', 'permission.v2.replied',
  'question.asked', 'question.replied', 'question.rejected',
  'question.v2.asked', 'question.v2.replied', 'question.v2.rejected',
  'session.next.prompted', 'session.next.prompt.admitted',
  'session.next.step.started', 'session.next.step.failed', 'session.next.tool.called',
]);

function report(event) {
  if (!process.env.TMUX || !process.env.TMUX_PANE || !event || !types.has(event.type)) return;
  const child = spawn(reporter, ['opencode'], { stdio: ['pipe', 'ignore', 'ignore'] });
  const timer = setTimeout(() => child.kill(), 3000);
  child.on('error', () => clearTimeout(timer));
  child.on('close', () => clearTimeout(timer));
  child.stdin.on('error', () => {});
  child.stdin.end(JSON.stringify(event));
}

function sessionID(event) {
  if (!event || typeof event !== 'object') return '';
  return event.sessionID || event.session_id || (event.session && event.session.id) || '';
}

async function v1Hooks() {
  return { event: async ({ event }) => report(event) };
}

const plugin = {
  id: 'tmux-canopy',
  async setup(ctx) {
    const controller = new AbortController();
    if (ctx.event && typeof ctx.event.subscribe === 'function') {
      void (async () => {
        try {
          for await (const event of ctx.event.subscribe({ signal: controller.signal })) report(event);
        } catch {
          // The subscription ends when OpenCode unloads the plugin.
        }
      })();
    }
    // Hooks observe the same lifecycle. They must not change effect, input, or prompt text.
    if (ctx.session && typeof ctx.session.hook === 'function') {
      await ctx.session.hook('prompt', (event) => {
        const id = sessionID(event);
        if (id) report({ type: 'session.next.prompted', properties: { sessionID: id }, location: event.location });
      });
    }
    if (ctx.tool && typeof ctx.tool.hook === 'function') {
      await ctx.tool.hook('execute.before', (event) => {
        const id = sessionID(event);
        if (id) report({ type: 'session.next.tool.called', properties: { sessionID: id, tool: event.tool } });
      });
    }
    if (ctx.permission && typeof ctx.permission.hook === 'function') {
      await ctx.permission.hook('evaluate', (event) => {
        // effect is left untouched. Without a request id, permission.v2.asked
        // on the event stream is the report that a later reply can clear.
        if (!event || event.effect !== 'ask') return;
        const id = sessionID(event);
        const requestID = event.id || event.requestID || '';
        if (!id || !requestID) return;
        report({
          type: 'permission.v2.asked',
          properties: {
            id: requestID,
            sessionID: id,
            action: event.action || '',
            resources: Array.isArray(event.resources) ? event.resources : [],
            metadata: event.metadata && typeof event.metadata === 'object' ? event.metadata : {},
          },
        });
      });
    }
    return () => controller.abort();
  },
  server: v1Hooks,
};

export default plugin;
export const CanopyPlugin = async () => v1Hooks();
