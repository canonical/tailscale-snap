# End to end testing: Tailscale, Headscale, Derper


## Deploy environment

For this testing, we'll use VMs on Azure.
This ensures we can test scenarios that are close to real world,
with public IP addresses and DNS names for Headscale and Derper.

This document deploys everything in the `australiaeast` region;
if you deploy in another region, substitute the name accordingly in domain names where referenced.


There is a provided Terraform module to deploy the environment,
or you can deploy it manually.
Both options are documented below:

### Deploy with Terraform

There is a Terraform module at [./e2e.tf](./e2e.tf) that will deploy the environment.

There are multiple ways to authenticate, but one way is to ensure the `az` command (azure cli) is installed and authenticated.
See https://learn.microsoft.com/en-gb/cli/azure/get-started-with-azure-cli for more information.

Then you will need `ARM_SUBSCRIPTION_ID` in the environment - see:
https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/azure_cli for details.
Example:

```bash
export ARM_SUBSCRIPTION_ID=466ee356-ce1f-11ef-bf94-db2a042e145c
```

Then you can apply through Terraform, providing required variables:

```bash
cd docs
terraform apply -var "ssh_key=YOUR PUBLIC SSH KEY CONTENTS"
```

Terraform will output an ssh config snippet,
with the configuration required to be able to ssh to the machines.
Please copy this to your ssh config in order to connect to the machines for the rest of the steps.

## Configure services

In this step, we will install all the required software, and configure them together.

A simple diagram of how the services are connected:

```text
Headscale -----> Derper (and Tailscale)
  ^
  |
  +------------+--------+
  |            |        |
Internal-1   User-1   User-2
  ^            ^        ^
  |            |        |
  |            +--------+
  |            |
Jumpbox-1    Jumpbox-2
```

All machines have a public ip address, except for Internal-1, User-1 and User-2.
User-1 and User-2 are on a separate network to the others, and cannot reach each other normally (without Tailscale).

### Configure Derper

```bash
ssh tailscale-etet-derper -- <<'EOF'
set -x
sudo snap install --edge derper
sudo snap set derper hostname=derper.australiaeast.cloudapp.azure.com
sudo snap restart derper
sudo snap logs derper
EOF

```

Once this is done, you should be able to visit https://derper.australiaeast.cloudapp.azure.com/ in your browser,
and see a generic public info page about the Tailscale DERP server.

### Configure Headscale

Configure Headscale with some custom policies to simulate some kind of company environment,
and to use only the custom DERP server.
For the policies, we're using a mix of users, groups, and tags to cover more features.

```bash
ssh tailscale-etet-headscale -- <<'GLOBALEOF'
set -x
sudo snap install --edge headscale

sudo tee /var/snap/headscale/common/config.yaml <<'EOF'
---
server_url: "https://headscale.australiaeast.cloudapp.azure.com"
listen_addr: "0.0.0.0:443"
# Address to listen to /metrics
metrics_listen_addr: "127.0.0.1:9090"
grpc_listen_addr: "127.0.0.1:50443"
noise:
  private_key_path: "/var/snap/headscale/common/internal/noise_private.key"
# List of IP prefixes to allocate tailaddresses from.
prefixes:
  v6: "fd7a:115c:a1e0::/48"
  v4: "100.64.0.0/10"
  allocation: sequential
derp:
  server:
    enabled: false
  urls: [] # default: https://controlplane.tailscale.com/derpmap/default
  paths:
    - "/var/snap/headscale/common/derp.yaml"
  auto_update_enabled: true
  update_frequency: 24h
disable_check_updates: true
ephemeral_node_inactivity_timeout: 30m
database:
  type: sqlite
  debug: false
  gorm:
    prepare_stmt: true
    parameterized_queries: true
    skip_err_record_not_found: true
    slow_threshold: 1000
  sqlite:
    path: "/var/snap/headscale/common/internal/db.sqlite"
    write_ahead_log: true
acme_url: https://acme-v02.api.letsencrypt.org/directory
acme_email: ""
tls_letsencrypt_hostname: "headscale.australiaeast.cloudapp.azure.com"
tls_letsencrypt_cache_dir: "/var/snap/headscale/common/internal/cache"
tls_letsencrypt_challenge_type: HTTP-01
tls_letsencrypt_listen: ":http"
log:
  format: text
  level: trace
policy:
  mode: file
  path: "/var/snap/headscale/common/policies.hujson"
dns:
  magic_dns: true
  base_domain: tailnet.internal
  nameservers:
    global:
      - 1.1.1.1
      - 1.0.0.1
      - 2606:4700:4700::1111
      - 2606:4700:4700::1001
    split:
      {}
  search_domains: []
  extra_records: []
unix_socket: "/var/snap/headscale/common/internal/headscale.sock"
unix_socket_permission: "0770"
EOF

sudo tee /var/snap/headscale/common/derp.yaml <<'EOF'
regions:
  900:
    regionid: 900
    regioncode: "one"
    regionname: "Custom Region One"
    nodes:
      - name: "1"
        regionid: 900
        hostname: "derper.australiaeast.cloudapp.azure.com"
EOF

sudo tee /var/snap/headscale/common/policies.hujson <<'EOF'
// reference docs: https://headscale.net/stable/ref/acls/
{
  "groups": {
    "group:users": ["user1", "user2"],
    "group:internal": ["internal"],
    "group:derper": ["derper"],
  },
  "tagOwners": {
    "tag:internal": ["group:internal"],
    "tag:derper": ["group:derper"],
  },
  "acls": [
    // ACL01 users can access internal servers and derper, but only over ssh
    {
      "action": "accept",
      "src": ["group:users"],
      "dst": [
        "tag:internal:22",
        "tag:derper:22",
      ]
    },
    // ACL02 user1 is an admin, and can access derper machines, and other ports on internal servers
    {
      "action": "accept",
      "src": ["user1"],
      "dst": [
        "tag:derper:*",
        "tag:internal:*",
      ]
    },
    // ACL03 internal servers can access each other
    {
      "action": "accept",
      "src": ["group:internal"],
      "dst": [
        "group:internal:*",
      ]
    },
    // ACL04 all machines can ping all other machines
    {
      "action": "accept",
      "src": ["*"],
      "proto": "icmp",
      "dst": [
        "*:*",
      ]
    // NOTES:
    //   Derper cannot access any servers; this will only be used for derper verify-clients (in the future; not implemented yet).
    //   No machines can access user machines.
    //   User machines cannot access each other.
    },
  ]
}
EOF

sudo snap restart headscale
sleep 2
sudo snap logs headscale
GLOBALEOF

```

You can also run a Headscale command to check if the config is valid:

```bash
ssh tailscale-etet-headscale -- sudo headscale configtest
```

This should not report any errors:

```text
2025-01-16T01:44:44Z INF Opening database database=sqlite3 path=/var/snap/headscale/common/internal/db.sqlite
```

Create the users for testing:

```bash
ssh tailscale-etet-headscale -- <<'EOF'
set -x
sudo headscale users create derper
sudo headscale users create internal
sudo headscale users create user1
sudo headscale users create user2
EOF

```

### Configure Tailscale

#### Configure Tailscale on machine internal-1

On internal-1, install Tailscale and authenticate to the Headscale server using a preauth key and user `internal` and tag `internal`.
In this environment, this simulates a jumpbox machine within a locked down datacenter (for example), that users such as operators and admins need to access.

```bash
KEY="$(ssh tailscale-etet-headscale -- sudo headscale preauthkeys create --user internal)"
echo "$KEY"

ssh tailscale-etet-internal-1 -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --advertise-tags tag:internal --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` above shows an ip address and the `internal` user.
Also verify that the DERP map printed only displays a single entry: the derper server we set up earlier.

Expected output:

```text
+ tailscale status
100.64.0.1      internal-1          internal        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```

#### Configure Tailscale on machine user-1

On user-1, install Tailscale and authenticate to the Headscale server using a preauth key and user `user1`.
In this environment, this simulates an end user machine like a laptop, owned by an admin user.

```bash
KEY="$(ssh tailscale-etet-headscale -- sudo headscale preauthkeys create --user user1)"
echo "$KEY"

ssh tailscale-etet-user-1 -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` above shows an ip address and the `internal` user.
Also verify that the DERP map printed only displays a single entry: the derper server we set up earlier.

Expected output:

```text
+ tailscale status
100.64.0.2      user-1               user1        linux   -
100.64.0.1      internal-1           internal     linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```

#### Configure Tailscale on machine user-2

On user-2, install Tailscale and authenticate to the Headscale server using the default interactive login flow (to test this login flow).
In this environment, this simulates an end user machine like a laptop, owned by an operator (non-admin) user.

```bash
ssh tailscale-etet-user-2 -- <<'EOF'
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com
EOF

```

The last command should print a long url on the Headscale server domain,
and wait (it will not exit until authentication is complete).
The url should look something like:

```text
https://headscale.australiaeast.cloudapp.azure.com/register/mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b
```

Navigate to this url to continue authentication.
The webpage should display a command to run on the Headscale server to authenticate the machine.
The text on the page should look something like:

> ## Machine registration
>
> Run the command below in the headscale server to add this machine to your network:
>
> ```text
> headscale nodes register --user USERNAME --key mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b
> ```

Replace `USERNAME` with the `user2` Headscale user,
then run it on the Headscale server VM.
Note that the long key displayed here is an example only; use the one actually displayed by the commnad.

```bash
ssh tailscale-etet-headscale -- sudo headscale nodes register --user user2 --key mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b
```

This command should output:

```text
... [debug logs]
Node user-2 registered
```

And the previous `tailscale up ...` command should exit with a success message:

```
+ sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com

To authenticate, visit:

        https://headscale.australiaeast.cloudapp.azure.com/register/mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b

Success.
```

Now we can double check that user-2 is now connected to the tailnet and also has the same DERP map configuration:

```bash
ssh tailscale-etet-user-2 -- <<'EOF'
set -x
tailscale status
tailscale debug derp-map
EOF

```

Expected output:

```text
+ tailscale status
100.64.0.3      user-2               user2        linux   -
100.64.0.1      internal-1           internal     linux   -
100.64.0.2      user-1               user1        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```

#### Configure Tailscale on machine derper

By default, Derper runs as an open relay.
It does have a `verify-clients` mode though, which uses a locally running Tailscale service to authenticate connections, to restrict use to machines in the same tailnet.
So here we configure Tailscale on the derper machine to support this.

NOTE: `verify-clients` mode is not currently supported in the Derper snap, so this is a provisional setup only: see https://github.com/canonical/derper-snap/pull/4 for progress.

On derper, install Tailscale and authenticate to the Headscale server using a preauth key with the `derper` user and tag `derper`:

```bash
KEY="$(ssh tailscale-etet-headscale -- sudo headscale preauthkeys create --user derper)"
echo "$KEY"

ssh tailscale-etet-derper -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --advertise-tags tag:derper --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` shows an ip address and the `derper` user for the `derper` machine.

Expected output:

```text
+ tailscale status
100.64.0.4      derper               derper       linux   -
100.64.0.1      internal-1           internal     linux   -
100.64.0.2      user-1               user1        linux   -
100.64.0.3      user-2               user2        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```

## Testing

### Test MagicDNS

Verify that the Headscale MagicDNS is working:

```bash
ssh tailscale-etet-user-1 -- resolvectl query --cache no --legen no internal-1.tailnet.internal
ssh tailscale-etet-user-1 -- resolvectl query --cache no --legen no internal-1
```

Both should return the same ip address (within the tailnet subnet).
Expected output:

```console
$ ssh tailscale-etet-user-1 -- resolvectl query --cache no --legen no internal-1.tailnet.internal
internal-1.tailnet.internal: 100.64.0.1                     -- link: tailscale0
$ ssh tailscale-etet-user-1 -- resolvectl query --cache no --legen no internal-1
internal-1: 100.64.0.1                                      -- link: tailscale0
            (internal-1.tailnet.internal)
```

This verifies that the Headscale dns service and search domain is configured as expected.

### Test tailnet connectivity from user-1 to internal-1

This is to verify that Tailscale is indeed providing a new connectivity path.

#### Setup

First, create and distribute an SSH key across the machines running Tailscale,
so we can test SSH over the tailnet.

```bash
ssh-keygen -f tailscale-etet-id.key -t ed25519 -N '' -C ubuntu@tailscale-etet-internal
for HOST in tailscale-etet-{internal-1,user-{1,2},derper}; do
  echo $HOST
  rsync tailscale-etet-id.key $HOST:.ssh/id_ed25519
  ssh $HOST -- tee -a .ssh/authorized_keys < tailscale-etet-id.key.pub
done
```

#### Test SSH without Tailscale

Take down Tailscale on the two machines:

```bash
ssh tailscale-etet-user-1 -- sudo tailscale down
ssh tailscale-etet-internal-1 -- sudo tailscale down
```

Attempt to SSH from user-1 to internal-1, via the internal-1 hostname:

```bash
ssh tailscale-etet-user-1 -- ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no internal-1 -- hostname
```

This should fail with the following message,
because the Tailscale DNS is not running:

```text
ssh: Could not resolve hostname internal-1: Temporary failure in name resolution
```

Attempt to SSH from user-1 to internal-1 again, this time via its private ip address:

```bash
IP="$(ssh tailscale-etet-internal-1 -- ip -br address show dev eth0 | awk '{ sub("/.*", "", $3); print $3; }')"
echo "$IP"
ssh tailscale-etet-user-1 -- ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no "$IP" -- hostname
```

This should also fail, this time with a timeout.
This is expected, since both machines are on separate private networks, with no routes between them.

```text
ssh: connect to host 10.0.1.5 port 22: Connection timed out
```

#### Test SSH with Tailscale

Bring Tailscale back up:

```bash
ssh tailscale-etet-user-1 -- sudo tailscale up
ssh tailscale-etet-internal-1 -- sudo tailscale up
```

Attempt to SSH from user-1 to internal-1, via the internal-1 hostname:

```bash
ssh tailscale-etet-user-1 -- $'ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no internal-1 -- echo $(hostname) to \'$(hostname)\''
```

This should succeed, and the expected output should be:

```text
user-1 to internal-1
```

Check the status of Tailscale:

```bash
ssh tailscale-etet-user-1 -- tailscale status
```

It should now show fresh information about the connection to internal-1:

```text
100.64.0.2      user-1               user1        linux   -
100.64.0.4      derper               derper       linux   -
100.64.0.1      internal-1           internal     linux   active; direct 4.196.101.99:1024, tx 6132 rx 6636
100.64.0.3      user-2               user2        linux   -
```

Tailscale should have managed to get a direct connection,
using the DERP server to help negotiate it.
See https://tailscale.com/kb/1257/connection-types for more information.
Although the two machines are on separate internal networks,
it's likely been able to succeed through a [NAT traversal strategy](https://tailscale.com/blog/how-nat-traversal-works).

### Test the DERP server

We can probe the DERP server from Tailscale,
to check it's configured and operating as expected.
This time, we'll test from user-2,
and we'll make some local firewall changes to prevent Tailscale from making a direct connection.

#### Quick test

First, we can use the `tailscale netcheck` subcommand:

```bash
ssh tailscale-etet-user-2 -- tailscale netcheck
```

This will output several lines,
but we're interested in the last few about DERP.
The output should look like this:

```text
Report:
        ...
        * Nearest DERP: Custom Region One
        * DERP latency:
                - one: 1.1ms   (Custom Region One)
```

This shows that the DERP server is reachable and operating.

#### Test relaying the connection over DERP

To test connection relaying over DERP,
we'll need to add some firewall rules to block Tailscale's NAT traversal techniques.
Temporarily enable `ufw` and deny all outgoing UDP traffic:

```bash
ssh tailscale-etet-user-2 -- <<'EOF'
set -x
yes | sudo ufw enable
sudo ufw allow ssh
sudo ufw deny out from any to any proto udp
sudo ufw status
EOF

```

Attempt to SSH from user-2 to internal-1:

```bash
ssh tailscale-etet-user-2 -- $'ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no internal-1 -- echo $(hostname) to \'$(hostname)\''
```

This should succeed, with output:

```text
user-2 to internal-1
```

Check Tailscale status:

```bash
ssh tailscale-etet-user-2 -- tailscale status
```

The output should show `relay` with the name of the custom DERP server ("one") for the `internal-1` machine:

```bash
100.64.0.2      user-1               user1        linux   -
100.64.0.4      derper               derper       linux   -
100.64.0.1      internal-1           internal     linux   active; relay "one", tx 12824 rx 13768
100.64.0.3      user-2               user2        linux   -
```

NOTE: if you had recently connected between `user-2` and `internal-1` over Tailscale,
before setting the firewall rules,
it may still display a direct connection.
This is probably due to the previous NAT traversal still being active.
In this case, wait a few minutes, and try SSH'ing and checking the status again.

You can also confirm a direct connection is not possible by using `tailscale ping`:

```bash
ssh tailscale-etet-user-2 -- tailscale ping internal-1
```

Expected output:

```text
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
pong from internal-1 (100.64.0.1) via DERP(one) in 4ms
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
pong from internal-1 (100.64.0.1) via DERP(one) in 2ms
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
pong from internal-1 (100.64.0.1) via DERP(one) in 2ms
pong from internal-1 (100.64.0.1) via DERP(one) in 3ms
direct connection not established
```

### Test policies

#### SSH connectivity rules

First, test some ACL policies by attempting to SSH between the machines, for all combinations of machines.

NOTE: several of the machines are on the same private network, so they can reach each other, regardless of the policies set by Tailscale.
Here, we're forcing SSH to use the tailscale interface by adding the `-B tailscale0` arguments.

```bash
ssh tailscale-etet-user-1 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no internal-1 -- echo $(hostname) to \'$(hostname)\' succeeds - ACL01'
ssh tailscale-etet-user-1 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no user-2 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
ssh tailscale-etet-user-1 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no derper -- echo $(hostname) to \'$(hostname)\' succeeds - ACL01 or ACL02'

ssh tailscale-etet-user-2 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no internal-1 -- echo $(hostname) to \'$(hostname)\' succeeds - ACL01'
ssh tailscale-etet-user-2 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no user-1 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
ssh tailscale-etet-user-2 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no derper -- echo $(hostname) to \'$(hostname)\' succeeds - ACL01'

ssh tailscale-etet-internal-1 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no user-1 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
ssh tailscale-etet-internal-1 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no user-2 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
ssh tailscale-etet-internal-1 -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no derper -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'

ssh tailscale-etet-derper -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no user-1 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
ssh tailscale-etet-derper -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no user-2 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
ssh tailscale-etet-derper -- $'ssh -B tailscale0 -o ConnectTimeout=2 -o StrictHostKeyChecking=no internal-1 -- echo $(hostname) to \'$(hostname)\' should fail with timeout - no ACL rule matches'
```

The expected output:

```text
user-1 to internal-1 succeeds - ACL01
ssh: connect to host user-2 port 22: Connection timed out
user-1 to derper succeeds - ACL01 or ACL02
user-2 to internal-1 succeeds - ACL01
ssh: connect to host user-1 port 22: Connection timed out
user-2 to derper succeeds - ACL01
ssh: connect to host user-1 port 22: Connection timed out
ssh: connect to host user-2 port 22: Connection timed out
ssh: connect to host derper port 22: Connection timed out
ssh: connect to host user-1 port 22: Connection timed out
ssh: connect to host user-2 port 22: Connection timed out
ssh: connect to host internal-1 port 22: Connection timed out
```

#### Port-based ACLs

Now we can test the port based ACLs.
According to ACL01, the `users` group can reach `derper` over port 22,
but according to ACL02, only `user1` can reach `derper` on other ports.

We've already verified in the previous section that `user-1` and `user-2` can both connect to `derper` over port 22 (SSH).
Now try connecting to the derper web page on port 80, from `user-1` - this should succeed due to ACL rule ACL01:

```bash
ssh tailscale-etet-user-1 -- curl --connect-timeout 2 -Is derper:80
```

Expected output:

```text
HTTP/1.1 302 Found
...
```

Try connecting to the same page from `user-2`.
This should fail, because there are no ACL rules that would permit `user-2` access to `derper` on port 80.

```bash
ssh tailscale-etet-user-2 -- curl --connect-timeout 2 derper:80
```

Expected output:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:--  0:00:02 --:--:--     0
curl: (28) Failed to connect to derper port 80 after 2002 ms: Timeout was reached
```
