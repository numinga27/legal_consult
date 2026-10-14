#!/usr/bin/env bash
# Compatibility entrypoint. The former 51.250.99.226 host is no longer used.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
exec bash "$script_dir/activate-recovery-domain.sh"
