#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 'ssh-rsa ...'"
  exit 1
fi

key="$1"

mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

if ! grep -qxF "$key" /root/.ssh/authorized_keys; then
  printf '%s\n' "$key" >> /root/.ssh/authorized_keys
fi

chown -R root:root /root/.ssh
