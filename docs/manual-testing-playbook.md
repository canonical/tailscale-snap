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

## Test smaller functionality

None of these are affected by snap confinement,
and should work as officially documented.

Test `tailscale netcheck`.
Expect a report with network information and a list of derp server latencies.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale netcheck
```

Test `tailscale ip`.
This should print the tailnet ips for the local machine.
They should match the ips shown for the `tailscale0` interface from `ip -br a`.

```bash
lxc exec $TAILSCALE_VM_1 -- ip -br a
lxc exec $TAILSCALE_VM_1 -- tailscale ip
```

Test `tailscale version`.
Expect the output to be the same as the snap version (maybe with a trailing revision).
If not, then the snap packaged the wrong tailscale version.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale version
```

Test `tailscale licenses`.
Expect this to simply print a message about open source licenses and a link to more information.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale licenses
```

Test `tailscale whois`.
Set `addr` to the tailnet address of another Tailscale machine.
You should see information about the target machine and Tailscale user.

```bash
addr=100.126.120.25
lxc exec $TAILSCALE_VM_1 -- tailscale whois $addr
```

Test `tailscale exit-node`.
These should succeed,
but they will probably list no exit nodes and no suggestions.

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale exit-node list
lxc exec $TAILSCALE_VM_1 -- tailscale exit-node suggest
```

Test `tailscale bugreport`.
Expect a long string starting with "BUG-" (printed as an identifier to use in bug reports).

```bash
lxc exec $TAILSCALE_VM_1 -- tailscale bugreport
```

Test bash completion.

```bash
vm="$TAILSCALE_VM_2"
lxc exec $vm -- bash

# In the vm:

# Type `tailscale ` and press tab twice. Verify that no tailscale-specific completion is offered.
# Then source the bash completion:

. /etc/bash_completion
. <( tailscale completion bash )
# Type `tailscale ` and press tab twice. Verify that you see tailscales-specific completion
```

...
