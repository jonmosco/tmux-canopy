// Copy this file to ~/.config/opencode/plugins/ and set the Canopy path.
import { spawn } from 'node:child_process';

const reporter = '/absolute/path/to/tmux-canopy/scripts/agent-hook';
const types = new Set(['session.created', 'session.status', 'session.idle',
  'permission.asked', 'permission.replied', 'session.error', 'session.deleted']);

export const CanopyPlugin = async () => ({
  event: async ({ event }) => {
    if (!process.env.TMUX || !process.env.TMUX_PANE || !types.has(event.type)) return;
    const child = spawn(reporter, ['opencode'], { stdio: ['pipe', 'ignore', 'ignore'] });
    const timer = setTimeout(() => child.kill(), 3000);
    child.on('error', () => clearTimeout(timer));
    child.on('close', () => clearTimeout(timer));
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(event));
  },
});
