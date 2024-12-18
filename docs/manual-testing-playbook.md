# Manual testing playbook

Document serves to describe the state of tailscale as packaged in the snap,
and to facilitate repeatable manual testing.

## Prerequisites

- LXD running on your local machine
- enough resources on your local machine to launch two VMs
- an account on https://tailscale.com
- a local tailscale snap file

## Setup

Global variables and settings (run this before anything else, configuring as desired):

```bash
set -x
TAILSCALE_VM_1="tailscale-1"
TAILSCALE_VM_2="tailscale-2"
TAILSCALE_SNAP_PATH=./tailscale_*_amd64.snap
```

Launch the VMs.
Note: we use VMs here, because it's more complex to get tailscale working in a container.
See https://tailscale.com/kb/1130/lxc-unprivileged and https://tailscale.com/kb/1112/userspace-networking for more information.

```bash
for vm in $TAILSCALE_VM_1 $TAILSCALE_VM_2; do
  lxc launch ubuntu:jammy $TAILSCALE_VM_1 --vm -c limits.cpu=1 -c limits.memory=4GiB
  lxc launch ubuntu:jammy $TAILSCALE_VM_2 --vm -c limits.cpu=1 -c limits.memory=4GiB
done
```

When the lxd vm agent is running (wait a few seconds),
then push and install the snap:

```bash
for vm in $TAILSCALE_VM_1 $TAILSCALE_VM_2; do
  lxc file push "$TAILSCALE_SNAP_PATH" "$vm/root/"
  lxc exec $vm -- sh -c 'snap install --dangerous ./tailscale_*.snap'
  lxc exec $vm -- snap connect tailscale:firewall-control
  lxc exec $vm -- snap connect tailscale:network-control
  lxc exec $vm -- snap connect tailscale:sys-devices-virtual-dmi-ids
  lxc exec $vm -- snap restart tailscale
  lxc exec $vm -- snap logs tailscale
  lxc exec $vm -- snap services
done
```

## Log in and bring up the tailnet

Log in to your account on the tailscale network
and bring the network up.
This should not be affected by snap confinement;
as in, it should work as in official docs.

```bash
for vm in $TAILSCALE_VM_1 $TAILSCALE_VM_2; do
  lxc exec $vm -- tailscale status
  lxc exec $vm -- tailscale up
  lxc exec $vm -- tailscale status
done
```

## Test functionality not affected by confinement

None of these are affected by snap confinement,
and should work as officially documented.

### Tailscale netcheck

Expect a report with network information and a list of derp server latencies.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale netcheck
```

### Tailscale ip

This should print the tailnet ips for the local machine.
They should match the ips shown for the `tailscale0` interface from `ip -br a`.

```bash
lxc exec $TAILSCALE_VM_1 -- ip -br a
lxc exec $TAILSCALE_VM_1 -- tailscale ip
```

### Tailscale version

Expect the output to be the same as the snap version (maybe with a trailing revision).
If not, then the snap packaged the wrong tailscale version.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale version
```

### Tailscale licenses

Expect this to simply print a message about open source licenses and a link to more information.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale licenses
```

### Tailscale whois

Set `addr` to the tailnet address of another Tailscale machine.
You should see information about the target machine and Tailscale user.

```bash
addr=100.126.120.25
lxc exec $TAILSCALE_VM_1 -- tailscale whois $addr
```

### Tailscale exit-node

These should succeed,
but they will probably list no exit nodes and no suggestions.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale exit-node list
lxc exec $TAILSCALE_VM_1 -- tailscale exit-node suggest
```

### Tailscale bugreport

Expect a long string starting with "BUG-" (printed as an identifier to use in bug reports).

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale bugreport
```

### Bash completion

```bash
lxc exec $TAILSCALE_VM_1 -- bash

# In the vm:

# Type `tailscale ` and press tab twice. Verify that no tailscale-specific completion is offered.
# Then source the bash completion:

. /etc/bash_completion
. <( tailscale completion bash )
# Type `tailscale ` and press tab twice. Verify that you see tailscales-specific completion
```

### tailscale nc

In one terminal:

```bash
lxc exec $TAILSCALE_VM_1 -- python3 -m http.server
```

And in another:

```bash
lxc exec $TAILSCALE_VM_2 -- sh -c "printf 'GET /\n\n' | tailscale nc $TAILSCALE_VM_1 8000"
```

You should see a log line from the python http server indicating a get request to `/`, with a `200` response.

---

TODO
working - not necessarily tested with all flags though:
- tailscale up
- tailscale down
- tailscale login
- tailscale logout
- tailscale web
- tailscale ping
- tailscale set
- tailscale serve
- tailscale funnel (it didn't work on "the internet" - I could still only resolve the domain in the tailnet, but nothing from the snap should be causing that)
- tailscale dns status


## Functionality affected by strict confinement

This functionality works to some extend,
but comes with some limitations due to strict confinement.

### Tailscale file copying

For copying a file from one tailscale machine to another.
This does work, but only for file and directory locations accessible by the snap.
For the tailscale snap, these paths will be:

- `SNAP_USER_COMMON`: `$HOME/snap/tailscale/common`
- `SNAP_USER_DATA`: `$HOME/snap/tailscale/x$N`
- `SNAP_COMMON`: `/var/snap/tailscale/common` (only writable if running tailscale as root)
- `SNAP_DATA`: `/var/snap/tailscale/x$N` (only writable if running tailscale as root)

See https://ubuntu.com/robotics/docs/snap-data-and-file-storage for more information on the file paths.

To test a successful case of file copying between hosts:

```bash
lxc exec $TAILSCALE_VM_1 -- sh -c "echo hello | tee snap/tailscale/common/greeting.txt"
lxc exec $TAILSCALE_VM_1 -- tailscale file cp snap/tailscale/common/greeting.txt $TAILSCALE_VM_2:

lxc exec $TAILSCALE_VM_2 -- tailscale file get -conflict overwrite snap/tailscale/common/
lxc exec $TAILSCALE_VM_2 -- cat snap/tailscale/common/greeting.txt  # expect "hello" output
```

To test a failure case - attempting to copy a file from a directory not readable by the Tailscale snap:

```bash
lxc exec $TAILSCALE_VM_1 -- sh -c "echo 'file in home dir' | tee home.txt"
lxc exec $TAILSCALE_VM_1 -- tailscale file cp home.txt $TAILSCALE_VM_2:
```

The result should be `open home.txt: permission denied`.

### Tailscale HTTPS certificates

To test this, you will need to enable the HTTPS certificates feature on your tailnet.
Navigate to https://login.tailscale.com/admin/dns, scroll down to "HTTPS Certificates", click "Enable HTTPS...", then click "Enable" to confirm.

Now we can test the default case of requesting a certificate for the local machine (this is expected to fail):

```bash
TAILNET_DOMAIN=$(lxc exec $TAILSCALE_VM_1 -- sh -c "tailscale dns status | awk 'match(\$0, /\w+\.ts\.net/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec $TAILSCALE_VM_1 -- tailscale cert $TAILSCALE_VM_1.$TAILNET_DOMAIN
```

The above command fails with a permission denied error on attempting to open a file in the home directory.
This is expected, and due to the strict confinement.
To workaround this, you can either output the cert files to stdout (this command should succeed):

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale cert --cert-file - --key-file - $TAILSCALE_VM_1.$TAILNET_DOMAIN
```

Or to a file within the directories accessible by the snap (this command should also succeed):

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale cert --cert-file ./snap/tailscale/common/cert.crt --key-file ./snap/tailscale/common/cert.key $TAILSCALE_VM_1.$TAILNET_DOMAIN
lxc exec $TAILSCALE_VM_1 -- ls ./snap/tailscale/common/
# cleanup
lxc exec $TAILSCALE_VM_1 -- rm ./snap/tailscale/common/cert.crt ./snap/tailscale/common/cert.key
```

## Functionality not working

This functionality does not work,
due to being strictly confined.

### Tailscale drive

For sharing a directory over webdav.
Sharing a drive does not work (although the command appears to succeed).
The drive management commands do work though: list, rename and unshare.

```bash
lxc exec $TAILSCALE_VM_1 -- mkdir snap/tailscale/common/drive
lxc exec $TAILSCALE_VM_1 -- tailscale drive share mydrive snap/tailscale/common/drive
lxc exec $TAILSCALE_VM_1 -- tailscale drive list  # mydrive listed
lxc exec $TAILSCALE_VM_1 -- tailscale drive rename mydrive mydrive2
lxc exec $TAILSCALE_VM_1 -- tailscale drive list  # mydrive2 listed
lxc exec $TAILSCALE_VM_1 -- tailscale drive unshare mydrive2
lxc exec $TAILSCALE_VM_1 -- tailscale drive list  # no drives listed
```

For an explanation of why sharing a drive doesn't work in the confined snap:

See
https://github.com/tailscale/tailscale/blob/e3c6ca43d3e3cad27714d07b3a9ec20141c9c65c/drive/driveimpl/remote_impl.go#L336-L355 .
Tailscaled in the snap is running as root, without access to su.
So the su check fails, and the check for running as non-root user also fails.
This is regardless of file paths and file permissions.
You can see the error messages in the tailscaled logs (`snap logs tailscale`).

### Tailscale dns

Tailscale manages the system DNS by default (it can be turned off via `tailscale set --accept-dns=false`).
It also provides a `tailscale dns` subcommand that can be used to test the resolver and view the status.

Check the status of the Tailscale DNS service on the host:

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale dns status
```

With the default configuration, this should indicate that Tailscale DNS is enabled, and print information about MagicDNS, Tailscale FQDN (fully qualified domain name) of the machine, DNS routes, and search domains.
You may see a note about "reading the system DNS configuration is not supported on this platform";
this does not appear to be related to snap confinement, merely a system limitation.

Now we can test resolving the Tailscale MagicDNS FQDN through the `tailscale dns query` subcommand,
as well as the system resolver.

```bash
TAILNET_DOMAIN=$(lxc exec $TAILSCALE_VM_1 -- sh -c "tailscale dns status | awk 'match(\$0, /\w+\.ts\.net/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec $TAILSCALE_VM_1 -- tailscale dns query $TAILSCALE_VM_2.$TAILNET_DOMAIN a
lxc exec $TAILSCALE_VM_1 -- dig $TAILSCALE_VM_2.$TAILNET_DOMAIN
```

Both of the above queries should return the same ipv4 address: the tailnet address of `TAILSCALE_VM_2`.
Resolvectl should confirm the system DNS settings applied by tailscale:

```bash
lxc exec $TAILSCALE_VM_1 -- resolvectl
```

Note that DNS queries for the bare machine name don't work (no result returned):

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale dns query $TAILSCALE_VM_2 a
lxc exec $TAILSCALE_VM_1 -- dig $TAILSCALE_VM_2
```

This is unexpected, but does not appear to be related to snap confinement.

### Tailscale SSH

TODO
- tailscaled in ssh mode does not work (incoming ssh connections on the tailnet will not work, failing with permission denied).
- `tailscale ssh` will work if sshing to a host running tailscaled, if that tailscaled is not installed via the strictly confined snap.

### Tailscale update

Tailscale includes a built in updater, which won't work because the snap files are immutable.
The behaviour will look like this (if a newer version of Tailscale is available):

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale update --yes
```

Output:

> open /etc/apt/sources.list.d/tailscale.list: no such file or directory

If Tailscale is already at the latest version, you will simply see a message about no updates needed.

## Unknowns

Untested; this playbook does not cover these cases.

- tailscale switch (untested - requires multiple accounts. no reason for it to not work though, since the login/logout commands work.)
- tailscale configure kubeconfig (untested - requires k8s server. This may not work if requires file paths, etc., but the command is alpha)
- tailscale lock
