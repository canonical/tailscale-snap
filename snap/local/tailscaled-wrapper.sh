#!/bin/sh -e

# Get proxy settings
HTTP_PROXY="$(snapctl get http-proxy)"
HTTPS_PROXY="$(snapctl get https-proxy)"
NO_PROXY="$(snapctl get no-proxy)"

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

exec "$SNAP/bin/tailscaled" "$@"
