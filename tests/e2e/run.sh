#!/usr/bin/env bash

set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$repo_root"

terraform_dir="$repo_root/.terraform/e2e"
export TF_DATA_DIR="$terraform_dir/data"
terraform_state_path="$terraform_dir/terraform.tfstate"

terraform_started=0

cleanup() {
    local status=$?
    trap - EXIT
    if (( terraform_started )) && [[ ${KEEP_ENV:-0} != 1 ]]; then
        if ! terraform -chdir=tests/e2e destroy -auto-approve && (( status == 0 )); then
            status=1
        fi
    fi
    exit "$status"
}
trap cleanup EXIT

shopt -s nullglob
snaps=(derper_*.snap)
if (( ${#snaps[@]} != 1 )); then
    printf 'Expected exactly one derper_*.snap artifact, found %d\n' "${#snaps[@]}" >&2
    exit 1
fi
derper_snap_path="$repo_root/${snaps[0]}"

snaps=(tailscale_*.snap)
if (( ${#snaps[@]} != 1 )); then
    printf 'Expected exactly one tailscale_*.snap artifact, found %d\n' "${#snaps[@]}" >&2
    exit 1
fi
tailscale_snap_path="$repo_root/${snaps[0]}"

snaps=(headscale_*.snap)
if (( ${#snaps[@]} != 1 )); then
    printf 'Expected exactly one headscale_*.snap artifact, found %d\n' "${#snaps[@]}" >&2
    exit 1
fi
headscale_snap_path="$repo_root/${snaps[0]}"

printf 'Using derper snap: %s\n' "$derper_snap_path"
printf 'Using tailscale snap: %s\n' "$tailscale_snap_path"
printf 'Using headscale snap: %s\n' "$headscale_snap_path"

terraform_started=1
mkdir -p "$terraform_dir"
terraform -chdir=tests/e2e init -backend-config="path=$terraform_state_path"
terraform -chdir=tests/e2e apply -auto-approve

DERPER_TEST_SNAP="$derper_snap_path" \
TAILSCALE_TEST_SNAP="$tailscale_snap_path" \
HEADSCALE_TEST_SNAP="$headscale_snap_path" \
    uv run --project tests/e2e pytest -vx tests/e2e/test_snap.py
