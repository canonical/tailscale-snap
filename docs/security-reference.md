# Security

Please see https://tailscale.com/security for information about security of Tailscale itself.
For this snap, it is strictly confined, to limit the impact if the binaries are compromised.
The following interfaces are connected for tailscaled (the daemon):

* network: for network access, this is required as tailscaled must communicate with external services (coordination server, etc.) and manage network traffic.
* network-bind: required because tailscaled binds to a UDP port for wireguard / peer-to-peer traffic.
* firewall-control: required for using iptables to restrict traffic to the tun device, to avoid interference from other networking software.
* network-control: required for configuring the network and access to /dev/net/tun. Tailscaled needs this to set up networking rules for the wiregard config and such (routing, attaching networks, etc.).
* sys-devices-virtual-info: a custom system-files read-only interface for files tailscaled needs to determine the platform it's running on. Without this, tailscaled will run, but may have issues in some environments.
* tpm: provides read/write access to `/dev/tpm*` and `/dev/tpmrm*` for TPM-backed node state encryption and hardware attestation.

And for tailscale (the client tool):

* network: general network access.
* network-bind: required for `tailscale web`.

The snap config or hooks do not directly use any cryptographic functions.

## Security hardening guidance

On devices with a functioning TPM 2.0, enable node state encryption with
`sudo snap set tailscale encrypt-state=true` to protect against state theft from
disk and node cloning. The encrypted state is bound to the original TPM, so
backups cannot be restored on a different TPM. Disabling encryption requires the
original working TPM to migrate the state back to plaintext.
See [Tailscale on the Snap Store](https://snapcraft.io/tailscale) for configuration
and [secure node state storage](https://tailscale.com/kb/1596/secure-node-state-storage)
for recovery guidance. This snap's state file is at
`/var/snap/tailscale/common/tailscaled.state`.

Enable hardware attestation with `sudo snap set tailscale hardware-attestation=true`
to bind node identity to the device using TPM-backed keys. This is independent of
state encryption and does not encrypt the state file by itself. The keys require
the original TPM and cannot be migrated to another device.
See [Tailscale on the Snap Store](https://snapcraft.io/tailscale) for configuration.

For more information on security hardening for Tailscale itself,
please refer to the following in the official Tailscale documentation:

- [Production best practices](https://tailscale.com/kb/1300/production-best-practices): a collection of documents with guidelines on running Tailscale in production, including hardening guidance.
- [Best practices to secure your tailnet](https://tailscale.com/kb/1196/security-hardening): a document with a list of best practices for hardening Tailscale.
