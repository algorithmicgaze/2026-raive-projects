#!/usr/bin/env bash
# Writes .env from .env.template, resolving op:// references through 1Password.
set -euo pipefail
cd "$(dirname "$0")"

op inject -f -i .env.template -o .env
chmod 600 .env
echo "wrote $(pwd)/.env"
