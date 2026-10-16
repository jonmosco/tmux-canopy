# Canopy demo storyboard and review

The recorder is [`record.py`](record.py), not a mockup. It builds fictional projects and agent events on a private tmux server and records an attached client; it never records your real sessions. Keys are checked against `scripts/ui-options.sh` (`j/k`, `h/l`, `/`, `p`, `4`, `n`) and the plugin toggle (`prefix + T` in `tmux-canopy.tmux`). Keep the scenes tied to those bindings when they change.

## README preview (~19 seconds)

| Beat | On screen | Evidence to review |
|---|---|---|
| Open | Quiet Tree, three projects, balanced content panes | The first published frame already shows the sidebar, not a bare terminal or a loading state. |
| Context | Two subagents appear under the API agent | `Explore` and `Plan` are beneath their actual parent pane; the footer stays readable at README width. |
| Attention | Web agent requests `npm run e2e` | The request and `!` appear on the web pane; tmux's transient alert is not mistaken for persistent sidebar state. |
| Action | `n` jumps to the waiting agent | The active session changes to `acme-web`; the last frame remains on the product, not a detach screen. |

## Longer walkthrough

Open the Tree; browse and fold with `j/k/h/l`; search with `/`, clear search, and open the preview with `p`; watch the API subagents appear; use `4` for Agents view; show the web agent's request and `n` jump; close the sidebar and reopen Canopy in popup mode. Each new view should remain onscreen long enough to read at README width. If a key starts acting differently, change the storyboard *and* the driver rather than publishing the wrong view.

## Rehearse, record, verify, publish

```bash
python3 docs/demo/record.py --smoke                         # same actions in an attached pty; no GIF
python3 docs/demo/record.py --output /tmp/canopy-demo-review
python3 docs/demo/verify.py /tmp/canopy-demo-review/*.gif --output /tmp/canopy-demo-frames
```

The `--smoke` and recording paths assert real milestones (Tree, subagents, request, cross-session jump, Agents view and popup). The verifier **coalesces** every GIF frame before producing numbered contact sheets; plain GIF frame extraction contains partial frames. Read **every** contact-sheet tile, and open its full-size `frame-NNN.png` whenever text or a transition is ambiguous. Also inspect both GIFs at the README's displayed width, the preview still, and `.cast` files for paths, project names, secrets, shell errors or unexpected content. The recorder blocks known absolute home/project/fixture paths but cannot judge whether fictional-looking text is safe to publish.

Only after review, copy the GIFs and still image to `docs/assets/` and update the README cache-busting `?v=` number. Keep `.cast` files out of git (see `.gitignore`); they are reproducible intermediate artifacts. The README preview is clipped after the attached sidebar has painted, and the ending is held on a useful view; a blank start, sustained half-drawn view, wrong scene or detach frame is a failed take. Brief partial frames during a real tmux popup opening are expected; check their duration before accepting them.

Recording requires tmux, fzf, asciinema 3, agg and Python 3 (plus `gsleep` on macOS); the verifier needs ImageMagick's `magick` command. These are **development tools only**, not dependencies for Canopy users.
