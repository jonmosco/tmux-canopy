// Copy this single file to ~/.pi/agent/extensions/ and set the Canopy path.
import { spawn } from 'node:child_process';

const reporter = '/absolute/path/to/tmux-canopy/scripts/agent-hook';
const kind = 'pi'; // Use 'omp' when installing under Oh My Pi.

export default function (pi: any) {
  async function report(type: string, ctx: any) {
    if (!process.env.TMUX || !process.env.TMUX_PANE) return;
    const session_id = ctx.sessionManager.getSessionId();
    if (!session_id) return;
    await new Promise<void>((resolve) => {
      const child = spawn(reporter, [kind], { stdio: ['pipe', 'ignore', 'ignore'] });
      const timer = setTimeout(() => child.kill(), 3000);
      child.on('error', () => { clearTimeout(timer); resolve(); });
      child.on('close', () => { clearTimeout(timer); resolve(); });
      child.stdin.on('error', () => {});
      child.stdin.end(JSON.stringify({ type, session_id }));
    });
  }
  pi.on('session_start', async (_event: any, ctx: any) => report('session_start', ctx));
  pi.on('agent_start', async (_event: any, ctx: any) => report('agent_start', ctx));
  pi.on('agent_end', async (_event: any, ctx: any) => report('agent_end', ctx));
  pi.on('session_shutdown', async (_event: any, ctx: any) => report('session_shutdown', ctx));
}
