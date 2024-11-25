# Tailscale snap

This repository contains the snap package sources for [Tailscale](https://github.com/tailscale/tailscale).

## Build the snap


You can build the snap locally with:

```
snapcraft --use-lxd
```

## Confinement

The snap is strictly confined, and requires the following interfaces:

### tailscale (the client)

- [network](https://snapcraft.io/docs/network-interface): general network access.
- [network-bind](https://snapcraft.io/docs/network-bind-interface): required for `tailscale web`.

### tailscaled (the daemon)

- [firewall-control](https://snapcraft.io/docs/firewall-control-interface): required for setting firewall rules. If this interface is not present, tailscaled will crash.
- [network](https://snapcraft.io/docs/network-interface): for network access, this is required as tailscaled must communicate with external services (coordination server, etc.) and manage network traffic
- [network-bind](https://snapcraft.io/docs/network-bind-interface): required because tailscaled binds to a UDP port for wireguard / peer-to-peer traffic.
- [network-control](https://snapcraft.io/docs/network-control-interface): required for configuring the network and access to /dev/net/tun. Tailscaled needs this to set up networking rules for the wiregard config and such (routing, attaching networks, etc.).
- `sys-devices-virtual-info`: a custom [system-files](https://snapcraft.io/docs/system-files-interface) read-only interface for files tailscaled needs to determine the platform it's running on.

## License

This packaging repository is released under the BSD 3-Clause "New" or "Revised" license.

Tailscale is released under the BSD 3-Clause "New" or "Revised" license.
Please see the upstream repository for more information: https://github.com/tailscale/tailscale/
