# syntax=docker/dockerfile:1
# A disposable tmux with Canopy loaded, for trying it out and recording demos.
# Build from the repository root, then run it in your terminal:
#
#   docker build -f docs/demo/Dockerfile -t canopy-demo .
#   docker run --rm -it canopy-demo
#
# Press Ctrl-a T to open Canopy, and Ctrl-a | to split a pane side by side. Exiting tmux removes the container.

# tmux is built from source: Canopy is tested with 3.7c, newer than the
# distribution's package.
FROM debian:trixie-slim AS tmux
ARG TMUX_VERSION=3.7c
ARG TMUX_SHA256=7c60cae9a0e25288e2e24750aafc9e8800fc7fd4555e447e1b29ee4201cfb3bf
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential bison pkg-config libevent-dev libncurses-dev \
      ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSL --retry 3 -o tmux.tar.gz \
      "https://github.com/tmux/tmux/releases/download/${TMUX_VERSION}/tmux-${TMUX_VERSION}.tar.gz" \
 && echo "${TMUX_SHA256}  tmux.tar.gz" | sha256sum --check \
 && tar -xzf tmux.tar.gz \
 && cd "tmux-${TMUX_VERSION}" \
 && ./configure --prefix=/usr/local \
 && make -j"$(nproc)" \
 && make install

FROM debian:trixie-slim
ARG TARGETARCH
ARG FZF_VERSION=0.74.4
# What Canopy uses (Bash, awk, ps, less), Python for the agent adapters, git
# for branch labels, and a UTF-8 locale so glyphs reach the terminal intact.
RUN apt-get update \
 && apt-get install -y --no-install-recommends bash gawk procps less python3 git ca-certificates curl \
      libevent-core-2.1-7t64 libncursesw6 locales ncurses-term \
 && sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen \
 && rm -rf /var/lib/apt/lists/*
COPY --from=tmux /usr/local/bin/tmux /usr/local/bin/tmux
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) sha=05e6813a337cc722c3ed07e54a764b75cc5d671e2e60459db0ba696ee5fa7504 ;; \
      arm64) sha=5d673b849f494f0d64ec471d8640b153ca8849e3846a31da17abdcfce8df6b46 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    cd /tmp; \
    curl -fsSL --retry 3 -o fzf.tar.gz \
      "https://github.com/junegunn/fzf/releases/download/v${FZF_VERSION}/fzf-${FZF_VERSION}-linux_${TARGETARCH}.tar.gz"; \
    echo "${sha}  fzf.tar.gz" | sha256sum --check; \
    tar -xzf fzf.tar.gz && install -m755 fzf /usr/local/bin/fzf && rm -f fzf fzf.tar.gz; \
    tmux -V && fzf --version

ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 TERM=xterm-256color
COPY . /opt/tmux-canopy
RUN useradd --create-home --shell /bin/bash demo
USER demo
WORKDIR /home/demo

# A few fictional projects, with branches, for the tree to show.
RUN set -eu; \
    git config --global user.name demo && git config --global user.email demo@example.com; \
    for project in acme-api:main acme-web:feature/settings notes:; do \
      name=${project%%:*}; branch=${project#*:}; mkdir -p "$name/src"; \
      if [ -n "$branch" ]; then git -C "$name" init -q -b "$branch" && git -C "$name" commit -q --allow-empty -m start; fi; \
    done

# Canopy's settings for demos; change them here or at prefix-: inside tmux.
COPY --chown=demo <<'EOF' /home/demo/.tmux.conf
set -g default-terminal tmux-256color
set -g prefix C-a
unbind C-b
bind C-a send-prefix
bind | split-window -h -c '#{pane_current_path}'
set -g mouse on
set -g escape-time 10
set -g @tmux-canopy-appearance quiet
set -g @tmux-canopy-icon-theme nerdfont
set -g @tmux-canopy-agents on
set -g @tmux-canopy-git-context branch
run-shell /opt/tmux-canopy/tmux-canopy.tmux
EOF

CMD ["bash", "-c", "cd ~/acme-api && tmux new-session -d -s acme-api -n server && tmux new-window -d -t acme-api: -n tests -c ~/acme-api/src && tmux new-session -d -s acme-web -n ui -c ~/acme-web && tmux new-session -d -s notes -n today -c ~/notes && exec tmux attach -t acme-api"]
