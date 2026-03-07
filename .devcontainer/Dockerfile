FROM mcr.microsoft.com/devcontainers/python:3.13

# Install apt packages (ffmpeg, libturbojpeg0, libpcap-dev)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libturbojpeg0 \
    libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Node LTS
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
USER vscode
RUN curl -fsSL https://claude.ai/install.sh | bash

# Install Playwright Chromium browser
RUN npx --yes playwright install chrome

USER root
