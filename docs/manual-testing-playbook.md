# Manual testing playbook

This document serves to describe the state of tailscale as packaged in the snap,
and to facilitate repeatable manual testing.

There are many shell code snippets in this document,
designed for you to be able to copy and paste into your shell.
Assuming the following prerequisites are met,
you should be able to follow the document,
running the snippets in order,
to verify everything described here.

> [!WARNING]
> Be careful which account and tailnet you use for testing.
> The test instructions include adding machines
> and changing tailnet settings which may impact functionality or security compliance.
> It's not recommended to run this testing on a production tailnet.


## Setup

### Prerequisites

- LXD running on your local machine
- enough resources on your local machine to launch two VMs
- an account on https://tailscale.com
- a local tailscale snap file (optional; you can also install from the snapstore)

### Set up the environment

For help with debugging, it's recommended to `set -x` in the shell,
so that the commands run are printed before they are executed:

```bash
set -x
```

Launch the VMs.
Note: VMs are used here, because it's more complex to get tailscale working in a container.
See https://tailscale.com/kb/1130/lxc-unprivileged and https://tailscale.com/kb/1112/userspace-networking for more information.

```bash
for vm in tailscale-1 tailscale-2; do
  lxc launch ubuntu:jammy $vm --vm -c limits.cpu=1 -c limits.memory=4GiB
done
```

### Install the Tailscale snap

Wait a few seconds for the LXD VM agent to be running,
then you can install the snap.

If installing the snap from a local file,
then push and install the snap.
You will also need to manually connect the interfaces,
as in the following script:

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

Or if installing from the snap store:

```bash
for vm in tailscale-1 tailscale-2; do
  lxc exec $vm -- snap install --edge tailscale
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

## Functionality not impacted by strict confinement

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
  Name:          tailscale-2.taild111.ts.net
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


### Tailscale syspolicy

The `tailscale syspolicy <...>` subcommands are related to how Tailscale can be customized with system policies.
See https://tailscale.com/kb/1080/cli#syspolicy and https://tailscale.com/kb/1315/mdm-keys for more information.

```bash
tailscale syspolicy list
```

With the default policies, this command will output something like this:

```text
No policy settings
```

This command is expected to show information about system policies if any are set, and any errors relating to them on the local machine.

The system policies can also be manually reapplied to the local machine by running:

```bash
tailscale syspolicy reload
```

Again, with the default policies, the command will simply output:

```text
No policy settings
```

### Tailscale metrics

Tailscale provides metrics; to view them, run:

```bash
tailscale metrics
```

The output should look like Prometheus metrics:

```text
$ tailscale metrics
# TYPE tailscaled_advertised_routes gauge
# HELP tailscaled_advertised_routes Number of advertised network routes (e.g. by a subnet router)
tailscaled_advertised_routes 0
...
# TYPE tailscaled_outbound_packets_total counter
# HELP tailscaled_outbound_packets_total Counts the number of packets sent to other peers
tailscaled_outbound_packets_total{path="derp"} 888
tailscaled_outbound_packets_total{path="direct_ipv4"} 0
tailscaled_outbound_packets_total{path="direct_ipv6"} 0
```

To check the validity of the metrics, you can use `promtool`:

```bash
sudo apt install -y prometheus
tailscale metrics | promtool check metrics
```

On success, there should be no output, and a zero exit code from `promtool`.



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

Click the link and authorize the login.
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


### Tailnet lock

[Tailnet lock](https://tailscale.com/kb/1226/tailnet-lock) is a way to manage nodes added to the tailnet,
without needing to trust the control server.

> [!WARNING]
> Avoid testing this on a production tailnet: once tailnet lock is enabled,
> it's enabled for the whole tailnet, and it cannot be disabled if the disablement keys are lost.

To begin testing, first logout of tailscale on `tailscale-2`:

```bash
lxc exec tailscale-2 -- tailscale logout
```

Now back on `tailscale-1`, verify that tailnet lock is not enabled:
```bash
lxc exec tailscale-1 -- tailscale lock status  # verify that tailnet lock is not enabled
```

Expected output:

```text
Tailnet lock is NOT enabled.

This node's tailnet-lock key: tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9
```

Then initialize tailnet lock, with the current machine as a trusted machine:

```bash
TAILSCALE_1_LOCK_KEY=$(lxc exec tailscale-1 -- sh -c "tailscale lock status | awk 'match(\$0, /tlpub:\w+/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec tailscale-1 -- sh -c "tailscale lock init --confirm --gen-disablements 3 $TAILSCALE_1_LOCK_KEY | tee tailnet-lock-disablements.txt"
```

Example output:

```text
You are initializing tailnet lock with the following trusted signing keys:
 - tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9 (25519 key)

3 disablement secrets have been generated and are printed below. Take note of them now, they WILL NOT be shown again.
        disablement-secret:37DC14689CE017B8302630413E5FC53C0C11E92FA4D92E6CA7550EEC6FDCCB57
        disablement-secret:B9353A77A79B72252A89AF9CB4C7BC1555FE92AE6079618D3145CC2310E33D99
        disablement-secret:095A4D50CDF0B7871EA224206CF770711A77B38242BE79A900D787071549A145
Initialization complete.
```

Note that the command above has saved the disablement secrets to `tailnet-lock-disablements.txt` on `tailscale-1`.
If these secrets are lost, it is impossible to disable tailnet lock for this tailnet.
It's possible to optionally add the flag `--gen-disablement-for-support` to the `tailscale lock init` subcommand,
which also sends a disablement key to Tailscale support,
which they can use to disable tailnet lock for you if required.

Now you can check the lock status on the machine and verify that it's enabled:

```bash
lxc exec tailscale-1 -- tailscale lock status
```

Example output:

```text
Tailnet lock is ENABLED.

This node is accessible under tailnet lock. Node signature:
SigKind: direct
Pubkey: [ZkEY1]
KeyID: tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9
WrappingPubkey: tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9

This node's tailnet-lock key: tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9

Trusted signing keys:
        tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9  1       (self)
```

Now you can add the second machine to the tailnet:

```bash
lxc exec tailscale-2 -- tailscale up
```

Click the login link and authorize the machine.
Verify that you see a message about being logged in, but not connected to the tailnet.

Example output:

```text
To authenticate, visit:

        https://login.tailscale.com/a/77fb5ab018fa7

Success.
this node is locked out; it will not have connectivity until it is signed. For more info, see https://tailscale.com/s/locked-out
```

You can check the status of Tailscale on both machines to see what this looks like:

```bash
lxc exec tailscale-1 -- tailscale status
lxc exec tailscale-2 -- tailscale status
```

The output from `tailscale-1` should not show an entry for `tailscale-2`,
and the output from `tailscale-2` should show both, but also a message about being locked out.

Example output:

```text
$ lxc exec tailscale-1 -- tailscale status
100.125.133.64  tailscale-1          user@ linux   -

$ lxc exec tailscale-2 -- tailscale status
100.110.164.126 tailscale-2          user@ linux   -
100.125.133.64  tailscale-1          user@ linux   -

# Health check:
#     - this node is locked out; it will not have connectivity until it is signed. For more info, see https://tailscale.com/s/locked-out
```

The first thing to do to sign the node is to check the output of `tailscale lock status`:

```bash
lxc exec tailscale-2 -- tailscale lock status
```

This will display the node key, signing key of the current node, and an example command to run to sign the node.
Example output:

```text
Tailnet lock is ENABLED.

This node is LOCKED OUT by tailnet-lock, and action is required to establish connectivity.
Run the following command on a node with a trusted key:
        tailscale lock sign nodekey:525d7760d26e79c515636f6959eb09a6356bd406a66d18c5f418f5d1863af371 tlpub:a1fb0f730ee636f15d71564451574ed599c4541a36b46bda585cd34491e90d80

This node's tailnet-lock key: tlpub:a1fb0f730ee636f15d71564451574ed599c4541a36b46bda585cd34491e90d80

Trusted signing keys:
        tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9  1
```

The default example command signs the node, allowing it access to the tailnet,
and adds the new node's tailnet-lock key as a rotation key.
You can run that command on the `tailscale-1` machine:

```bash
TAILSCALE_2_SIGN_CMD=$(lxc exec tailscale-2 -- sh -c "tailscale lock status | awk 'match(\$0, /tailscale lock sign .+/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec tailscale-1 -- $TAILSCALE_2_SIGN_CMD
```

This command will have no output if successful,
but you can check by re-running the status and lock status subcommands:

```bash
lxc exec tailscale-1 -- tailscale status
lxc exec tailscale-2 -- tailscale status
lxc exec tailscale-2 -- tailscale lock status
```

`tailscale-2` is expected to be visible from `tailscale-1` now,
and the lock status on `tailscale-2` is expected to show that tailnet lock is enabled and the node is accessible.
Example output:

```text
$ lxc exec tailscale-1 -- tailscale status
100.125.133.64  tailscale-1          user@ linux   -
100.110.164.126 tailscale-2          user@ linux   -

$ lxc exec tailscale-2 -- tailscale status
100.110.164.126 tailscale-2          user@ linux   -
100.125.133.64  tailscale-1          user@ linux   -

$ lxc exec tailscale-2 -- tailscale lock status
Tailnet lock is ENABLED.

This node is accessible under tailnet lock. Node signature:
SigKind: direct
Pubkey: [bm7gg]
KeyID: tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9
WrappingPubkey: tlpub:8867e1b69fdd1a7eb53e2a63ae5b464b305fb1072f814c56873b34d73c94bb63

This node's tailnet-lock key: tlpub:8867e1b69fdd1a7eb53e2a63ae5b464b305fb1072f814c56873b34d73c94bb63

Trusted signing keys:
        tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9  1
```


Now add the second machine as a signing key to tailnet lock.
First try to add it from `tailscale-2`:

```bash
TAILSCALE_2_LOCK_KEY=$(lxc exec tailscale-2 -- sh -c "tailscale lock status | awk 'match(\$0, /tailnet-lock key: tlpub:\w+/) {print substr(\$0, RSTART+18, RLENGTH); exit}'")
lxc exec tailscale-2 -- tailscale lock add $TAILSCALE_2_LOCK_KEY
```

This is expected to fail,
because `tailscale-2` isn't a signing node - ie. it doesn't have a trusted tailnet lock key.
Expected output:

```text
error: 500 Internal Server Error: network-lock modify failed: modify network-lock keys: this node does not have a trusted tailnet lock key
```

Now try to add it to `tailscale-1`:

```bash
TAILSCALE_2_LOCK_KEY=$(lxc exec tailscale-2 -- sh -c "tailscale lock status | awk 'match(\$0, /tailnet-lock key: tlpub:\w+/) {print substr(\$0, RSTART+18, RLENGTH); exit}'")
lxc exec tailscale-1 -- tailscale lock add $TAILSCALE_2_LOCK_KEY
```

This command is expected to not print any output if successful.
You can check the lock status to verify that there are now two trusted signing keys:

```bash
lxc exec tailscale-1 -- tailscale lock status
```

Example output:

```text
Tailnet lock is ENABLED.
...

Trusted signing keys:
        tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9  1       (self)
        tlpub:8867e1b69fdd1a7eb53e2a63ae5b464b305fb1072f814c56873b34d73c94bb63  1
```

Also, in the Tailscale web admin, both machines now should display a "Signing node" label.

Now you can test removing `tailscale-2` as a trusted signing key.

```bash
TAILSCALE_2_LOCK_KEY=$(lxc exec tailscale-2 -- sh -c "tailscale lock status | awk 'match(\$0, /tailnet-lock key: tlpub:\w+/) {print substr(\$0, RSTART+18, RLENGTH); exit}'")
lxc exec tailscale-1 -- tailscale lock remove $TAILSCALE_2_LOCK_KEY
```

No output is expected from successful completion of the command.
And now check the lock status to verify the signing key has been removed:

```bash
lxc exec tailscale-1 -- tailscale lock status
```

Example output:

```text
Tailnet lock is ENABLED.
...

Trusted signing keys:
        tlpub:9a317ca81d417453698173947f98882e1d875dd37e84458181ed9632232238f9  1       (self)
```

Tailnet lock also has a log of changes made.
This includes events like adding or removing signing keys.
Note that it does not include adding or removing nodes from the tailnet.

```bash
lxc exec tailscale-1 -- tailscale lock log
```

Example output:

```text
update 97c937da8a2f1f68dec712487536099b68a862b4bbeb5bb536b6ae26107808e3 (remove-key)
KeyID: 8867e1b69fdd1a7eb53e2a63ae5b464b305fb1072f814c56873b34d73c94bb63

update 6b0ec9a18149fce42cb581cf5059a30666edce300580ded82d3613495b5fc208 (add-key)
Type: 25519
KeyID: 8867e1b69fdd1a7eb53e2a63ae5b464b305fb1072f814c56873b34d73c94bb63

update 9ba396b37e01e8421bf47710e414c650e984ee421043388ec7aa3e0700969a8d (checkpoint)
...
```

To disable tailnet lock, you will need one of the disablement keys
generated when running `tailscale lock init`.
These were saved to `tailnet-lock-disablements.txt`,
so you can extract one from that file and disable the tailnet lock:

```bash
DISABLEMENT_SECRET="$(lxc exec tailscale-1 -- sh -c "awk 'match(\$0, /disablement-secret:\w+/) {print substr(\$0, RSTART, RLENGTH); exit}' < tailnet-lock-disablements.txt")"
lxc exec tailscale-1 -- tailscale lock disable "$DISABLEMENT_SECRET"
```

This command will not output anything if successful.

Now verify that tailnet lock is no longer enabled,
from the perspective of both machines:

```bash
lxc exec tailscale-1 -- tailscale lock status
lxc exec tailscale-2 -- tailscale lock status
```

Expected output:

```text
Tailnet lock is NOT enabled.
...
```

Note that sometimes, at this point Tailscale on a machine has been observed to think that tailnet lock is still enabled,
perhaps due to caching.
If you see that, you can fix it by running `tailscale down` followed by `tailscale up`:

```
lxc exec tailscale-1 -- tailscale down
lxc exec tailscale-1 -- tailscale up
```

Finally, both machines should still be active on the tailnet and be aware of each other:

```bash
lxc exec tailscale-1 -- tailscale status
lxc exec tailscale-2 -- tailscale status
lxc exec tailscale-1 -- tailscale ping tailscale-2
lxc exec tailscale-2 -- tailscale ping tailscale-1
```

Example output:

```text
100.125.133.64  tailscale-1          user@ linux   -
100.110.164.126 tailscale-2          user@ linux   active; direct 10.177.175.233:51104
100.110.164.126 tailscale-2          user@ linux   -
100.125.133.64  tailscale-1          user@ linux   active; direct 10.177.175.146:35839
pong from tailscale-2 (100.110.164.126) via 10.177.175.233:51104 in 1ms
pong from tailscale-1 (100.125.133.64) via 10.177.175.146:35839 in 1ms
```

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

Now you can test resolving the Tailscale MagicDNS FQDN through the `tailscale dns query` subcommand,
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

## Functionality impacted by strict confinement

This functionality works,
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

Now you can test the default case of requesting a certificate for the local machine (this is expected to fail):

```bash
TAILNET_DOMAIN=$(lxc exec tailscale-1 -- sh -c "tailscale dns status | awk 'match(\$0, /\w+\.ts\.net/) {print substr(\$0, RSTART, RLENGTH); exit}'")
lxc exec tailscale-1 -- tailscale cert tailscale-1.$TAILNET_DOMAIN
```

Output:

> open ./tailscale-1.taild11111.ts.net.crt.tmp2631737963: permission denied

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

### Debug subcommands

Tailscale also provides several subcommands for debugging.
Note that these commands are not publicly documented, and not guaranteed to be stable.

```text
$ tailscale debug --help
Debug commands

USAGE
  tailscale debug <debug-flags | subcommand>

"tailscale debug" contains misc debug facilities; it is not a stable interface.

SUBCOMMANDS
  derp-map               Print DERP map
  component-logs         Enable/disable debug logs for a component
  daemon-goroutines      Print tailscaled's goroutines
  daemon-logs            Watch tailscaled's server logs
  metrics                Print tailscaled's metrics
  env                    Print cmd/tailscale environment
  stat                   Stat a file
  hostinfo               Print hostinfo
  local-creds            Print how to access Tailscale LocalAPI
  restun                 Force a magicsock restun
  rebind                 Force a magicsock rebind
  derp-set-on-demand     Enable DERP on-demand mode (breaks reachability)
  derp-unset-on-demand   Disable DERP on-demand mode
  break-tcp-conns        Break any open TCP connections from the daemon
  break-derp-conns       Break any open DERP connections from the daemon
  pick-new-derp          Switch to some other random DERP home region for a short time
  force-prefer-derp      Prefer the given region ID if reachable (until restart, or 0 to clear)
  force-netmap-update    Force a full no-op netmap update (for load testing)
  reload-config          Reload config
  control-knobs          See current control knobs
  prefs                  Print prefs
  watch-ipn              Subscribe to IPN message bus
  netmap                 Print the current network map
  via                    Convert between site-specific IPv4 CIDRs and IPv6 'via' routes
  ts2021                 Debug ts2021 protocol connectivity
  set-expire             Manipulate node key expiry for testing
  dev-store-set          Set a key/value pair during development
  derp                   Test a DERP configuration
  capture                Streams pcaps for debugging
  portmap                Run portmap debugging
  peer-endpoint-changes  Prints debug information about a peer's endpoint changes
  dial-types             Prints debug information about connecting to a given host or IP
  resolve                Does a DNS lookup
  go-buildinfo           Prints Go's runtime/debug.BuildInfo

FLAGS
  --cpu-profile string
        if non-empty, grab a CPU profile for --profile-seconds seconds and write it to this file; - for stdout
  --file string
        get, delete:NAME, or NAME
  --mem-profile string
        if non-empty, grab a memory profile and write it to this file; - for stdout
  --profile-seconds int
        number of seconds to run a CPU profile for, when --cpu-profile is non-empty (default 15)
```

Most of these commands simply print debug information, and are expected to work fine in the snap.
Some are designed to make changes for debugging, and have not been extensively tested.
Some output to a file (eg. `--cpu-profile <file>`) - these have the standard restrictions on file locations for strictly confined snaps (see https://snapcraft.io/docs/data-locations).

Some have issues however:

#### tailscale debug local-creds

`tailscale debug local-creds` advertises an incorrect path to the control socket:

```text
$ tailscale debug local-creds
curl --unix-socket /var/run/tailscale/tailscaled.sock http://local-tailscaled.sock/localapi/v0/status
```

Since this is running from the snap, with a custom socket path provided, the curl command should actually be:

```bash
curl --unix-socket /var/snap/tailscale/common/socket/tailscaled.sock http://local-tailscaled.sock/localapi/v0/status
```

#### tailscale debug capture

This will not work, due to the strictly confined environment not including wireshark.
Tailscale will not be able to access wireshark, even if wireshark is installed on the system:

```text
$ sudo tailscale debug capture
exec: "wireshark": executable file not found in $PATH
```

## Functionality not supported in strict confinement

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

## Cleanup

To cleanup, you can remove the machines from the Tailscale web admin console, on the "Machines" tab.

Then delete the LXD VMs:

```bash
lxc delete --force tailscale-1 tailscale-2
```

## Unknowns

Untested cases that are not covered in this playbook:

- `tailscale switch`: This requires multiple accounts. This is expected to work, since the login/logout sub commands work.
- `tailscale configure kubeconfig`: This requires a Kubernetes cluster. This may not work if requires certain file paths, but otherwise may work.
- `tailscale lock disablement-kdf`, `tailscale lock local-disable`, `tailscale lock revoke-keys`: These were not in scope of testing in this document, but they are expected to work.
- Custom configuration options (arguments to `tailscale up`, `tailscale login`, or `tailscale set`): As noted in an earlier section, there are many options. `--ssh` is known to not work, but the others are expected to work.
