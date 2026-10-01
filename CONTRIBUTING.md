# Contributing to Canopy

Thanks for your interest in Canopy. Bug reports, ideas, documentation fixes, and pull requests are all welcome, and you don't need to be a tmux expert to help.

## Reporting a bug

Open an [issue](https://github.com/jonmosco/tmux-canopy/issues) and include what you can of:

- What you did, what you expected, and what happened instead.
- Your OS, and your tmux, fzf, and Bash versions.
- The output of `~/.tmux/plugins/tmux-canopy/canopy doctor` (adjust the path if you installed elsewhere).
- For agent problems, which agent and whether its Canopy integration is installed (`canopy integration status`).

Screenshots are helpful. Please check them for private project names, hostnames, or terminal output first.

## Suggesting a feature

Open an issue describing what you're trying to do. For larger changes, such as a new view, a new agent integration, or anything that changes how Canopy interacts with your tmux setup, it helps to talk it through in an issue before writing much code, so we can agree on the approach first.

Canopy aims to stay:

- **Daemon-free:** everything runs in response to tmux events or keys.
- **Additive:** it enhances your tmux workflow without changing what your status line shows or taking over your key bindings. Where a feature needs a tmux option set, such as alert monitoring for sidebar notifications, Canopy saves your value, keeps the visible result the same, and restores it when the feature is turned off.
- **Light on your system:** the sidebar refreshes often, on your own machine, so Canopy starts as few processes as it can and relies only on tmux, fzf, Bash, awk, and standard system tools. A change that adds a new dependency, or a command run for every pane or every refresh, needs a good reason. [AGENTS.md](AGENTS.md#keep-processes-and-tools-to-a-minimum) lists the specific techniques.

Ideas that fit these are the easiest to take on.

## Making a change

1. Fork the repository and create a branch.
2. Make your change. Matching the style of the surrounding code is appreciated.
3. Run the tests:

   ```bash
   bash tests/run.sh
   ```

   They need tmux, fzf, Bash 4.4+, Python 3, and ShellCheck (and Homebrew `coreutils` on macOS). Each suite runs on its own private tmux server, so your sessions are not touched. You can run one suite with, for example, `python3 tests/buffers.py`.
4. If you can, add a test for the behavior you changed, and update the README, `docs/reference.md`, or `CHANGELOG.md` where users would notice the difference. If you're unsure about tests or docs, open the pull request anyway and we'll sort it out together.
5. Open a pull request describing what changed and why. Screenshots or a short recording help for visual changes.

[AGENTS.md](AGENTS.md) has more detail on the code layout and conventions.

## Using AI tools

AI coding assistants are welcome here; Canopy itself is developed with their help. If a tool wrote a meaningful part of your change, please mention it in the pull request so reviewers have the context. Either way, make sure you understand the change and can explain it, since reviewers may ask about it.

## License

By contributing, you agree that your contributions are licensed under the [Apache License, Version 2.0](LICENSE), the same license as the project.
