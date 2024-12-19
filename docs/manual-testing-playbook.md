# Manual testing playbook

This document serves to describe the state of tailscale as packaged in the snap,
and to facilitate repeatable manual testing.

There are many shell code snippets in this document,
designed for you to be able to copy and paste into your shell.
Assuming the following prerequisites are met,
you should be able to follow the document,
running the snippets in order,
to verify everything described here.

### Prerequisites

- LXD running on your local machine
- enough resources on your local machine to launch two VMs
- an account on https://tailscale.com
- a local tailscale snap file

## Setup

For help with debugging, it's recommended to `set -x` in the shell,
so that the commands run are printed before they are executed:

```bash
set -x
```

Launch the VMs.
Note: we use VMs here, because it's more complex to get tailscale working in a container.
See https://tailscale.com/kb/1130/lxc-unprivileged and https://tailscale.com/kb/1112/userspace-networking for more information.

```bash
for vm in tailscale-1 tailscale-2; do
  lxc launch ubuntu:jammy tailscale-1 --vm -c limits.cpu=1 -c limits.memory=4GiB
  lxc launch ubuntu:jammy tailscale-2 --vm -c limits.cpu=1 -c limits.memory=4GiB
done
```

Wait a few seconds for the LXD VM agent to be running,
then push and install the snap:

```bash
# adjust path as needed
TAILSCALE_SNAP_PATH=./tailscale_*_amd64.snap

for vm in tailscale-1 tailscale-2; do
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

### Bring up the tailnet

Now that everything is installed,
you can use `tailscale up` to bring up the network.
This should not be affected by snap confinement;
as in, it should work as in official docs.
Note that this command will also prompt for authentication;
when it does, please click the authentication link and confirm it.

```bash
for vm in tailscale-1 tailscale-2; do
  lxc exec $vm -- tailscale status
  lxc exec $vm -- tailscale up
  lxc exec $vm -- tailscale status
done
```

## Functionality not affected by confinement

None of these are affected by snap confinement,
and should work as officially documented.

### Tailscale netcheck

Expect a report with network information and a list of derp server latencies.

```bash
lxc exec tailscale-1 -- tailscale netcheck
```

Output example:

```text
Report:
        * UDP: true
        * IPv4: yes, 61.245.148.199:38896
...
```

### Tailscale ip

This should print the tailnet ips for the local machine.
They should match the ips shown for the `tailscale0` interface from `ip -br a`.

```bash
lxc exec tailscale-1 -- ip -br a show tailscale0
lxc exec tailscale-1 -- tailscale ip
```

### Tailscale version

Expect the output to be the same as the snap version (maybe with a trailing revision).
If not, then the snap packaged the wrong tailscale version.

```bash
lxc exec tailscale-1 -- tailscale version
```

Output example:

```text
1.76.6-dev20241104
  tailscale commit: 1edcf9d466ceafedd2816db1a24d5ba4b0b18a5b
  go version: go1.23.3
```

### Tailscale licenses

This simply prints a message about open source licenses and a link to more information.

```bash
lxc exec tailscale-1 -- tailscale licenses
```

Expected output:

```text
Tailscale wouldn't be possible without the contributions of thousands of open
source developers. To see the open source packages included in Tailscale and
their respective license information, visit:

    https://tailscale.com/licenses/tailscale
```

### Tailscale whois

Set `addr` to the tailnet address of another Tailscale machine.
You should see information about the target machine and Tailscale user.

```bash
addr=100.126.120.25
lxc exec tailscale-1 -- tailscale whois $addr
```

Example output (redacted):

```text
Machine:
  Name:          tailscale-2.taild....ts.net
  ID:            ...
  Addresses:     [100.../32 fd7a:.../128]
User:
  Name:     ...
  ID:       ...
```

### Tailscale exit-node

These should succeed,
but they will probably list no exit nodes and no suggestions.

```bash
lxc exec tailscale-1 -- tailscale exit-node list
lxc exec tailscale-1 -- tailscale exit-node suggest
```

Example output:

```text
no exit nodes found

No exit node suggestion is available.
```

### Tailscale bugreport

This simply prints a unique identifier to use in bug reports.

```bash
lxc exec tailscale-1 -- tailscale bugreport
```

Example expected output:

```text
BUG-4db3f...
```

### Bash completion

```bash
lxc exec tailscale-1 -- bash

# In the vm:

# Type `tailscale ` and press tab twice. Verify that no tailscale-specific completion is offered.
# Then source the bash completion:

. /etc/bash_completion
. <( tailscale completion bash )
# Type `tailscale ` and press tab twice. Verify that you see tailscale-specific completion
```

Example:

```text
$ tailscale <TAB><TAB>
bugreport   (Print a shareable identifier to help diagnose issues)
cert        (Get TLS certs)
completion  (Shell tab-completion scripts)
configure   ([ALPHA] Configure the host to enable more Tailscale features)
...
```

### Tailscale nc

In one terminal:

```bash
lxc exec tailscale-1 -- python3 -m http.server
```

And in another:

```bash
lxc exec tailscale-2 -- sh -c "printf 'GET /\n\n' | tailscale nc tailscale-1 8000"
```

You should see a log line from the python http server indicating a get request to `/`, with a `200` response.

### Tailscale web

Tailscale web runs a web server that you can use to control tailscaled.

To test this, you can run this to start the server:

```bash
lxc exec tailscale-1 -- tailscale web --listen 0.0.0.0:8088
```

Example output:

```text
2024/12/18 04:54:12 web server running on: http://0.0.0.0:8088
```

And navigate to the lxd network ip address of the VM at port 8088 in your local web browser.
You should see a webpage with information about tailscale on the machine.
It is expected to be in "viewing" mode, if you're accessing from a host machine that isn't in logged into the same tailnet with tailscale.

When finished, you can press `ctrl+c` in the terminal to interrupt and stop the web server.

### Tailscale ping

This provides a way to ping other machines on the tailnet:

```bash
lxc exec tailscale-1 -- tailscale ping tailscale-2
```

Example output:

```text
pong from tailscale-2 (100.108.34.59) via 10.177.175.233:38425 in 1ms
```

### Tailscale up and tailscale down

These subcommands are for bringing the network up and down,
without re-authentication required.

To test `tailscale down`:

```bash
lxc exec tailscale-1 -- tailscale down
lxc exec tailscale-1 -- ip -br address show tailscale0
```

Verify that the `ip -br address show` command shows either no addresses, or only an ipv6 link local address.
The machine is no longer connected to the tailnet.

To test `tailscale up`:

```bash
lxc exec tailscale-1 -- tailscale up
lxc exec tailscale-1 -- ip -br address show tailscale0
```

Verify that the tailnet was brought up on the machine without any reauthentication required,
and that `ip -br address` shows the tailnet addresses.

### Tailscale login and tailscale logout

These subcommands are for logging out and in,
taking the network down when logging out,
and requiring authentication and bringing the network back up when logging in.

To test `tailscale logout`:

```bash
lxc exec tailscale-1 -- tailscale logout
lxc exec tailscale-1 -- ip -br address show tailscale0
```

Verify that the `ip -br address show` command shows either no addresses, or only an ipv6 link local address.
The machine is no longer connected to the tailnet.

To test `tailscale login`:

```bash
lxc exec tailscale-1 -- tailscale login
```

You should see the authentication request - example output:

```text
To authenticate, visit:

        https://login.tailscale.com/a/redacted
```

Click the link and authorise the login.
Then you can check the network on the machine again:

```bash
lxc exec tailscale-1 -- ip -br address show tailscale0
```

Verify that `ip -br address` above shows the tailnet addresses.

### Tailscale serve

`tailscale serve` acts as a reverse proxy for a local HTTP/S server,
to expose it securely within the tailnet.

To test this, run this example webserver in one terminal:

```bash
lxc exec tailscale-1 -- mkdir tmp-server
lxc exec tailscale-1 -- touch tmp-server/test-file-1.txt
lxc exec tailscale-1 --cwd /root/tmp-server -- python3 -m http.server --bind 127.0.0.1 8000
```

And run the tailscale serve process in another terminal:

```bash
lxc exec tailscale-1 -- tailscale serve 8000
```

Example output:

```text
Available within your tailnet:

https://tailscale-1.taild11111.ts.net/
|-- proxy http://127.0.0.1:8000

Press Ctrl+C to exit.
```

And finally in a third terminal, test you can reach the server from the second VM:

```bash
TAILNET_DOMAIN=$(lxc exec tailscale-1 -- sh -c "tailscale dns status | awk 'match(\$0, /\w+\.ts\.net/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec tailscale-2 -- curl https://tailscale-1.$TAILNET_DOMAIN
```

Verify you see an HTML response of a directory listing including the `test-file-1.txt` created above.

Try to navigate to the https tailnet url from your local web browser (on a machine connected to the internet, but not to the tailnet),
and verify that it is not accessible.

### Tailscale funnel

`tailscale funnel` acts as a reverse proxy for a local HTTP/S server,
to expose it securely to the public internet.

To test this, run this example webserver in one terminal:

```bash
lxc exec tailscale-1 -- mkdir tmp-server2
lxc exec tailscale-1 -- touch tmp-server2/test-file-2.txt
lxc exec tailscale-1 --cwd /root/tmp-server2 -- python3 -m http.server --bind 127.0.0.1 8000
```

And run the tailscale funnel process in another terminal:

```bash
lxc exec tailscale-1 -- tailscale funnel 8000
```

Example output:

```text
Funnel is not enabled on your tailnet.
To enable, visit:

         https://login.tailscale.com/f/funnel?node=1111B111111111T1L
```

Funnel is not enabled on a tailnet by default.
Please configure it now by navigating to the url printed by the command,
and clicking the "Enable" button to confirm.

Once you have enabled it, the `tailscale funnel` command should print more output
to confirm that it is now working:

```text
...
Success.
Available on the internet:

https://tailscale-1.taild11111.ts.net/
|-- proxy http://127.0.0.1:8000

Press Ctrl+C to exit.
```

Try to navigate to the https tailnet url from your local web browser (on a machine connected to the internet, but not to the tailnet),
and verify you see an HTML response of a directory listing including the `test-file-2.txt` created above.
This verifies that the proxied service is indeed visible to the internet.

Note: the [Tailscale funnel docs](https://tailscale.com/kb/1223/funnel#dns-propagation) state
that you may need to wait up to 10 minutes for DNS records to propagate,
before you can access the url.

> [!WARNING]
> In testing, the domain could not be resolved even after waiting longer than the 10 minutes.
> The cause is to be confirmed.


## Functionality affected by strict confinement

This functionality works to some extend,
but comes with some limitations due to strict confinement.

### Tailscale configuration options

Tailscale exposes some configuration options that can be managed
through `tailscale` subcommands.
For example, to use a custom control server,
whether to accept DNS config from the control server,
or to override the machine hostname.

These options can be set at any time using `tailscale set` with the desired arguments.
The options can also be set by passing extra arguments to `tailscale up` or `tailscale login`
when initially bringing up the network or logging in.

To see all the options supported on the various subcommands:

```bash
lxc exec tailscale-1 -- tailscale login -h
lxc exec tailscale-1 -- tailscale up -h
lxc exec tailscale-1 -- tailscale set -h
```

Due to the many possible combinations,
testing these options is out of scope for this document.
However, it is expected that almost all options will work correctly as expected in the strictly confined snap.
The only known option that will not work,
is `--ssh` (tailscaled ssh mode) - see the later section about Tailscale SSH.

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
lxc exec tailscale-1 -- sh -c "echo hello | tee snap/tailscale/common/greeting.txt"
lxc exec tailscale-1 -- tailscale file cp snap/tailscale/common/greeting.txt tailscale-2:

lxc exec tailscale-2 -- tailscale file get -conflict overwrite snap/tailscale/common/
lxc exec tailscale-2 -- cat snap/tailscale/common/greeting.txt  # expect "hello" output
```

To test a failure case - attempting to copy a file from a directory not readable by the Tailscale snap:

```bash
lxc exec tailscale-1 -- sh -c "echo 'file in home dir' | tee home.txt"
lxc exec tailscale-1 -- tailscale file cp home.txt tailscale-2:
```

The result should be `open home.txt: permission denied`.

### Tailscale HTTPS certificates

To test this, you will need to enable the HTTPS certificates feature on your tailnet.
Navigate to https://login.tailscale.com/admin/dns, scroll down to "HTTPS Certificates", click "Enable HTTPS...", then click "Enable" to confirm.

Now we can test the default case of requesting a certificate for the local machine (this is expected to fail):

```bash
TAILNET_DOMAIN=$(lxc exec tailscale-1 -- sh -c "tailscale dns status | awk 'match(\$0, /\w+\.ts\.net/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec tailscale-1 -- tailscale cert tailscale-1.$TAILNET_DOMAIN
```

Output:

> open ./tailscale-1.taild742dc.ts.net.crt.tmp2631737963: permission denied

This failure to create the cert file in the home directory is expected due to strict confinement.
To workaround this, you can either output the cert files to stdout (this command should succeed):

```bash
lxc exec tailscale-1 -- tailscale cert --cert-file - --key-file - tailscale-1.$TAILNET_DOMAIN
```

Output example:

```text
-----BEGIN CERTIFICATE-----
MIIDmjCCAyCgAwIBAgISA9asmzuogjk4Nz3...
...
```

Or to a file within the directories accessible by the snap (this command should also succeed):

```bash
lxc exec tailscale-1 -- tailscale cert --cert-file ./snap/tailscale/common/cert.crt --key-file ./snap/tailscale/common/cert.key tailscale-1.$TAILNET_DOMAIN
lxc exec tailscale-1 -- ls ./snap/tailscale/common/
```

## Functionality not working

This functionality does not work,
due to being strictly confined.

### Tailscale drive

For sharing a directory over webdav.
Sharing a drive does not work (although the command appears to succeed).
The drive management commands do work though: list, rename and unshare.

```bash
lxc exec tailscale-1 -- mkdir snap/tailscale/common/drive
lxc exec tailscale-1 -- tailscale drive share mydrive snap/tailscale/common/drive
lxc exec tailscale-1 -- tailscale drive list  # mydrive listed
lxc exec tailscale-1 -- tailscale drive rename mydrive mydrive2
lxc exec tailscale-1 -- tailscale drive list  # mydrive2 listed
lxc exec tailscale-1 -- tailscale drive unshare mydrive2
lxc exec tailscale-1 -- tailscale drive list  # no drives listed
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
lxc exec tailscale-1 -- tailscale dns status
```

With the default configuration, this should indicate that Tailscale DNS is enabled, and print information about MagicDNS, Tailscale FQDN (fully qualified domain name) of the machine, DNS routes, and search domains.
You may see a note about "reading the system DNS configuration is not supported on this platform";
this does not appear to be related to snap confinement, merely a system limitation.

Now we can test resolving the Tailscale MagicDNS FQDN through the `tailscale dns query` subcommand,
as well as the system resolver.

```bash
TAILNET_DOMAIN=$(lxc exec tailscale-1 -- sh -c "tailscale dns status | awk 'match(\$0, /\w+\.ts\.net/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec tailscale-1 -- tailscale dns query tailscale-2.$TAILNET_DOMAIN a
lxc exec tailscale-1 -- dig tailscale-2.$TAILNET_DOMAIN
```

Both of the above queries should return the same ipv4 address: the tailnet address of `TAILSCALE_VM_2`.
Resolvectl should confirm the system DNS settings applied by tailscale:

```bash
lxc exec tailscale-1 -- resolvectl
```

Note that DNS queries for the bare machine name don't work (no result returned):

```bash
lxc exec tailscale-1 -- tailscale dns query tailscale-2 a
lxc exec tailscale-1 -- dig tailscale-2
```

This is unexpected, but does not appear to be related to snap confinement.

### Tailscale SSH

- Tailscaled in ssh mode (ie. run with `--ssh`) does not work (incoming ssh connections on the tailnet will not work, failing with permission denied).
- `tailscale ssh` will work if sshing to a host running tailscaled, if that tailscaled is not installed via the strictly confined snap.

### Tailscale update

Tailscale includes a built in updater, which won't work because the snap files are immutable.
The behaviour will look like this (if a newer version of Tailscale is available):

```bash
lxc exec tailscale-1 -- tailscale update --yes
```

Output:

```text
open /etc/apt/sources.list.d/tailscale.list: no such file or directory
```

If Tailscale is already at the latest version, you will simply see a message about no updates needed.

## Unknowns

Untested cases that are not covered in this playbook:

- `tailscale switch`: This requires multiple accounts. No reason for it to not work though, since the login/logout sub commands work.
- `tailscale configure kubeconfig`: This requires a Kubernetes cluster. This may not work if requires certain file paths, but otherwise may work fine.
- `tailscale lock`: Untested, but should work correctly.
- Arguments to `tailscale up`, `tailscale login`, or `tailscale set`: As noted in an earlier section, there are many options. `--ssh` is known to not work, but the others should work.
