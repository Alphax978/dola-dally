#!/usr/bin/env bash
# ci/install.sh: install tools on a GitHub machine without ever hanging.
# Each attempt has a time limit; a stalled download is cut off and retried (3 tries).
#   bash ci/install.sh apt ffmpeg fonts-dejavu-core
#   bash ci/install.sh pip requests cryptography
#   bash ci/install.sh pip torch --index-url https://download.pytorch.org/whl/cpu
set -u
kind="$1"; shift
for attempt in 1 2 3; do
  start=$(date +%s)
  if [ "$kind" = "apt" ]; then
    # never let apt (or Ubuntu's restart helper) stop to ask a question: no one is there to answer
    APT="sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1 apt-get -o DPkg::Lock::Timeout=60 \
         -o Acquire::http::Timeout=20 -o Acquire::Retries=2 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
    timeout -k 10 180 $APT update -qq </dev/null \
      && timeout -k 10 300 $APT install -y -qq --no-install-recommends "$@" </dev/null && ok=1 || ok=0
  else
    timeout -k 10 420 pip install -q --progress-bar off --timeout 30 --retries 3 "$@" </dev/null && ok=1 || ok=0
  fi
  if [ "$ok" = 1 ]; then
    echo "installed ($kind) in $(( $(date +%s) - start ))s: $*"
    exit 0
  fi
  echo "::warning title=Install::$kind attempt $attempt failed or stalled after $(( $(date +%s) - start ))s; retrying"
  sleep 10
done
echo "::error title=Install::$kind install failed 3 times: $*"
exit 1
