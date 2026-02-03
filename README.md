# Tailscale snap

This repository contains the snap package sources for [Tailscale](https://github.com/tailscale/tailscale).

For user documentation for the snap, please see [Tailscale on the Snap Store](https://snapcraft.io/tailscale).
See below for developer documentation.

## Local development

You can build the snap locally with:

```
snapcraft --use-lxd
```

Then install it (dangerous mode is required for locally built snaps):

```
sudo snap install --dangerous ./tailscale_*.snap
```

In dangerous mode, these interfaces are not automatically connected,
so they must be manually connected:

```
sudo snap connect tailscale:firewall-control
sudo snap connect tailscale:network-control
sudo snap connect tailscale:sys-devices-virtual-dmi-ids
```

Once the interfaces are connected,
then you must restart the tailscaled service
(it will have failed without the interfaces):

```
sudo snap restart tailscale
```

Now you can manage tailscale with the `tailscale` command:

```
tailscale status
```

## Configuration

### Proxy settings

To configure proxy settings for `tailscaled`, use `snap set`, for example:

```
sudo snap set tailscale https-proxy=http://proxy.example.com:3128
sudo snap set tailscale http-proxy=http://proxy.example.com:3128
sudo snap set tailscale no-proxy=localhost,127.0.0.1
```

To remove a proxy setting:

```
sudo snap unset tailscale https-proxy
```

The service automatically restarts when proxy settings are changed.

## Integration with other snaps

Other snaps can access tailscaled via its unix socket through the `tailscale:socket` slot.
This slot exposes a content interface, which will be a directory containing the `tailscaled.sock` socket file.

For example, if there is a snap called `derper`,
and it has this plug definition:

```
plugs:
  tailscale-socket:
    interface: content
    content: socket-directory
    target: $SNAP_COMMON/tailscale-socket
```

Then you can integrate `derper` with `tailscale` like this:

```
$ sudo snap connect derper:tailscale-socket tailscale:socket
```

And the tailscaled socket will be available to the `derper` snap
as `$SNAP_COMMON/tailscale-socket/tailscaled.sock`.

## License

This packaging repository is released under the BSD 3-Clause "New" or "Revised" license.

Tailscale is released under the BSD 3-Clause "New" or "Revised" license.
Please see the upstream repository for more information: https://github.com/tailscale/tailscale/
