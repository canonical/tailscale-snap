#!/bin/sh -e

# Get proxy settings
HTTP_PROXY="$(snapctl get http-proxy)"
HTTPS_PROXY="$(snapctl get https-proxy)"
NO_PROXY="$(snapctl get no-proxy)"
NO_LOGS_NO_SUPPORT="$(snapctl get no-logs-no-support)"
ENCRYPT_STATE="$(snapctl get encrypt-state)"
HARDWARE_ATTESTATION="$(snapctl get hardware-attestation)"

# Export proxy settings
if [ -n "$HTTP_PROXY" ]; then
    export HTTP_PROXY
    export http_proxy="$HTTP_PROXY"
fi

if [ -n "$HTTPS_PROXY" ]; then
    export HTTPS_PROXY
    export https_proxy="$HTTPS_PROXY"
fi

if [ -n "$NO_PROXY" ]; then
    export NO_PROXY
    export no_proxy="$NO_PROXY"
fi

# Optional flags
EXTRA_FLAGS=""
if [ "$NO_LOGS_NO_SUPPORT" = "true" ]; then
    EXTRA_FLAGS="--no-logs-no-support"
fi
if [ "$ENCRYPT_STATE" = "true" ]; then
    EXTRA_FLAGS="$EXTRA_FLAGS --encrypt-state"
fi
if [ "$HARDWARE_ATTESTATION" = "true" ]; then
    EXTRA_FLAGS="$EXTRA_FLAGS --hardware-attestation"
fi

exec "$SNAP/bin/tailscaled" $EXTRA_FLAGS "$@"
