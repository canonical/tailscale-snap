# Security

Please see https://tailscale.com/security for information about security of Tailscale itself.
For this snap, it is strictly confined, to limit the impact if the binaries are compromised.
The following interfaces are connected for tailscaled (the daemon):

* network: for network access, this is required as tailscaled must communicate with external services (coordination server, etc.) and manage network traffic.
* network-bind: required because tailscaled binds to a UDP port for wireguard / peer-to-peer traffic.
* firewall-control: required for using iptables to restrict traffic to the tun device, to avoid interference from other networking software.
* network-control: required for configuring the network and access to /dev/net/tun. Tailscaled needs this to set up networking rules for the wiregard config and such (routing, attaching networks, etc.).
* sys-devices-virtual-info: a custom system-files read-only interface for files tailscaled needs to determine the platform it's running on. Without this, tailscaled will run, but may have issues in some environments.

And for tailscale (the client tool):

* network: general network access.
* network-bind: required for `tailscale web`.

The snap config or hooks do not directly use any cryptographic functions.

## Security hardening guidance

The snap does not provide any configuration,
and thus we have no specific hardening guidance to provide here.
For more information on security hardening for Tailscale itself,
please refer to the following in the official Tailscale documentation:

- [Production best practices](https://tailscale.com/kb/1300/production-best-practices): a collection of documents with guidelines on running Tailscale in production, including hardening guidance.
- [Best practices to secure your tailnet](https://tailscale.com/kb/1196/security-hardening): a document with a list of best practices for hardening Tailscale.
