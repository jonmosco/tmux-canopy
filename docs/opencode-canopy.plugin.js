// Observational OpenCode adapter. Copy to ~/.config/opencode/plugins/ and set the reporter path.
// OpenCode 1.x loads the default export as an async plugin function.
// Reports lifecycle state only. Never approves a permission, blocks a tool, or rewrites a prompt.
import { spawn } from 'node:child_process';

const reporter = '/absolute/path/to/tmux-canopy/scripts/agent-hook';
const types = new Set([
  'session.created', 'session.updated', 'session.deleted', 'session.status', 'session.idle', 'session.error',
  'permission.asked', 'permission.replied', 'permission.updated', 'permission.v2.asked', 'permission.v2.replied',
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

// Hooks are observational only. They do not change a permission decision,
// tool arguments, or prompt text. `event` supplies terminal states; the other
// hooks provide progress when an OpenCode release omits an event.
const plugin = async ({ directory }) => ({
  event: async ({ event }) => report(event),
  'chat.message': async ({ sessionID }) => {
    if (sessionID) report({
      type: 'session.next.prompted',
      properties: { sessionID },
      location: { directory },
    });
  },
  'tool.execute.before': async ({ sessionID, tool }) => {
    if (sessionID) report({
      type: 'session.next.tool.called',
      properties: { sessionID, tool },
      location: { directory },
    });
  },
  'permission.ask': async (permission) => {
    if (!permission || !permission.sessionID || !permission.id) return;
    report({
      type: 'permission.v2.asked',
      properties: {
        id: permission.id,
        sessionID: permission.sessionID,
        action: permission.action || permission.permission || '',
        resources: Array.isArray(permission.resources) ? permission.resources : permission.patterns || [],
        metadata: permission.metadata && typeof permission.metadata === 'object' ? permission.metadata : {},
      },
      location: { directory },
    });
  },
});

export default plugin;
export const CanopyPlugin = plugin;
