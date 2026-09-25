# README animation

The animation shows the actual Canopy sidebar on a private tmux server with generated sessions, files, terminal output, and buffers. The example application output is fictional. Nothing is captured from an existing tmux server.

## Regenerate

Use Linux with the project's tmux/fzf requirements, Python 3 with Pillow, Neovim, fontconfig, and a monospace Nerd Font (the preview uses Hack Nerd Font Mono):

```bash
python3 docs/demo/generate.py --theme dracula
```

An explicit font file can be supplied with `--font /path/to/font.ttf`. Use `--output /tmp/canopy-preview` to review a recording before replacing the README assets.

The generator creates an animated GIF, a still PNG, and a text capture audit. Only the GIF and PNG belong in `docs/assets`; the audit is ignored by Git. It uses an empty home directory, a clean environment, no personal tmux/Neovim configuration, and a unique socket that it removes on exit. Captures fail if they contain the invoking user's name, hostname, home-directory prefixes, or the project checkout path.

Before publishing, inspect the GIF and text audit for unexpected content and missing glyphs. The terminal colors use the chosen demo palette. This affects the preview only; it does not change your terminal settings. Explicit application colors (such as Canopy’s indexed selection background) remain intact. Captions and key hints are added outside the terminal area. The GIF loops; the README also links to the still image.

## Terminal themes

Dracula is the default for the README preview. Choose `--theme dracula`, `--theme catppuccin-mocha`, `--theme tokyo-night`, or `--theme canopy` (the original demo colors). The banner above the terminal is omitted; feature captions and shortcut hints remain below it.

ANSI colors and default backgrounds/foregrounds come from the official [Dracula](https://github.com/dracula/alacritty/blob/master/dracula.toml), [Catppuccin Mocha](https://github.com/catppuccin/alacritty/blob/main/catppuccin-mocha.toml), and [Tokyo Night](https://github.com/folke/tokyonight.nvim/blob/main/extras/alacritty/tokyonight_night.toml) terminal palettes. Muted text and the surrounding caption frame use demo-specific shades.

The preview uses 18-pixel terminal text in a 96-column layout, with full-resolution GIF and PNG assets. Click the README animation to open it at full size. Notification scenes show generated activity and bell events on fictional background panes.
