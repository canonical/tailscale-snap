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
Headscale -----> Derper [Tailscale also running]
  ^
  |
  +------------+
  |            |
Internal-1   Internal-2
  ^            ^
  |            |
  +------------+
  |            |
Jumpbox-1    Jumpbox-2
```

All machines have a public ip address, except for Internal-1 and Internal-2.
Internal-1 and Internal-2 are on separate networks, and cannot reach each other normally (without tailscale).

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
  path: ""
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
  use_username_in_magic_dns: false
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

sudo snap restart headscale
sleep 2
sudo snap logs headscale
GLOBALEOF

```

Create two initial users for testing:

```bash
ssh tailscale-etet-headscale -- <<'EOF'
set -x
sudo headscale users create user1
sudo headscale users create user2
EOF

```

We'll register Tailscale nodes internal-1 and internal-2 to user1,
and Tailscale on the derper node to user2.

### Configure Tailscale

#### Configure Tailscale on machine internal-1

On internal-1, install Tailscale and authenticate to the Headscale server using a preauth key and user `user1`:

```bash
KEY="$(ssh tailscale-etet-headscale -- sudo headscale preauthkeys create --user user1)"
ssh tailscale-etet-internal-1 -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` above shows an ip address and the `user1` tailnet.
Also verify that the DERP map printed only displays a single entry: the derper server we set up earlier.

Expected output:

```text
+ tailscale status
100.64.0.1      internal-1          user1        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```

#### Configure Tailscale on machine internal-2

On internal-2, install Tailscale and authenticate to the Headscale server using the default interactive login flow:

```bash
ssh tailscale-etet-internal-2 -- <<'EOF'
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

Replace `USERNAME` with the `user1` Headscale user,
then run it on the Headscale server VM.
Note that the long key displayed here is an example only; use the one actually displayed by the commnad.

```bash
ssh tailscale-etet-headscale -- sudo headscale nodes register --user user1 --key mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b
```

This command should output:

```text
... [debug logs]
Node internal-2 registered
```

And the previous `tailscale up ...` command should exit with a success message:

```
+ sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com

To authenticate, visit:

        https://headscale.australiaeast.cloudapp.azure.com/register/mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b

Success.
```

Now we can double check that internal-2 is now connected to the tailnet and also has the same DERP map configuration:

```bash
ssh tailscale-etet-internal-2 -- <<'EOF'
set -x
tailscale status
tailscale debug derp-map
EOF

```

Expected output:

```text
+ tailscale status
100.64.0.2      internal-2          user1        linux   -
100.64.0.1      internal-1          user1        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```


#### Configure Tailscale on machine derper

On derper, install Tailscale and authenticate to the Headscale server using a preauth key with the `user2` user:

```bash
KEY="$(ssh tailscale-etet-headscale -- sudo headscale preauthkeys create --user user2)"
ssh tailscale-etet-derper -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` shows an ip address and the `user2` tailnet for `derper`.

Expected output:

```text
+ tailscale status
100.64.0.3      derper              user2        linux   -
100.64.0.2      internal-2          user1        linux   -
100.64.0.1      internal-1          user1        linux   -
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
ssh tailscale-etet-internal-1 -- resolvectl query --cache no --legen no internal-2.tailnet.internal
ssh tailscale-etet-internal-1 -- resolvectl query --cache no --legen no internal-2
```

Both should return the same ip address (within the tailnet subnet).
Expected output:

```text
tailscale-2.tailnet.internal: 100.64.0.2                    -- link: tailscale0

tailscale-2: 100.64.0.2                                     -- link: tailscale0
             (tailscale-2.tailnet.internal)
```

This verifies that the Headscale dns service and search domain is configured as expected.

### Test tailnet connectivity between internal-1 and internal-2

This is to verify that Tailscale is indeed providing a new connectivity path.

#### Setup

First, create and distribute an SSH key across the machines running Tailscale,
so we can test SSH over the tailnet.

```bash
ssh-keygen -f tailscale-etet-id.key -t ed25519 -N '' -C ubuntu@tailscale-etet-internal
for HOST in tailscale-etet-{internal-{1,2},derper}; do
  echo $HOST
  rsync tailscale-etet-id.key $HOST:.ssh/id_ed25519
  ssh $HOST -- tee -a .ssh/authorized_keys < tailscale-etet-id.key.pub
done
```

#### SSH without Tailscale

Take down Tailscale on the two internal machines:

```bash
ssh tailscale-etet-internal-1 -- sudo tailscale down
ssh tailscale-etet-internal-2 -- sudo tailscale down
```

Attempt to SSH from internal-1 to internal-2, via the internal-2 hostname:

```bash
ssh tailscale-etet-internal-1 -- ssh -o StrictHostKeyChecking=no internal-2 -- hostname
```

This should fail with the following message,
because the Tailscale DNS is not running:

```text
ssh: Could not resolve hostname internal-2: Temporary failure in name resolution
```

Attempt to SSH from internal-1 to internal-2 again, this time via its private ip address:

```bash
IP="$(ssh tailscale-etet-internal-2 -- ip -br address show dev eth0 | awk '{ sub("/.*", "", $3); print $3; }')"
ssh tailscale-etet-internal-1 -- ssh -o StrictHostKeyChecking=no "$IP" -- hostname
```

This should also fail, this time with a timeout.
This is expected, since both machines are on separate private networks, with no routes between them.

```text
ssh: connect to host 10.1.2.5 port 22: Connection timed out
```

#### SSH with Tailscale

Bring Tailscale back up:

```bash
ssh tailscale-etet-internal-1 -- sudo tailscale up
ssh tailscale-etet-internal-2 -- sudo tailscale up
```

Attempt to SSH from internal-1 to internal-2, via the internal-2 hostname:

```bash
ssh tailscale-etet-internal-1 -- ssh -o StrictHostKeyChecking=no internal-2 -- hostname
```

This should succeed, and the output should be the result of running `hostname` on internal-2:

```text
internal-2
```

Check the status of Tailscale:

```bash
ssh tailscale-etet-internal-1 -- tailscale status
```

It should now show fresh information about the connection to internal-2:

```text
100.64.0.1      internal-1           user1        linux   -
100.64.0.3      derper               user2        linux   -
100.64.0.2      internal-2           user1        linux   active; direct 52.156.185.242:1024, tx 19372 rx 17988
```

Note that it shows a direct connection through some public IP address.
It's unknown what this means, as this is not the DERP relay.
Tailscale has managed to negotiate some kind of direct connection,
most likely using the DERP server to help negotiate it.

### Test the DERP server

We can probe the DERP server from Tailscale,
to check it's configured and operating as expected.

First, we can use the `tailscale netcheck` subcommand:

```bash
ssh tailscale-etet-internal-1 -- tailscale netcheck
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

TODO: figure out what firewall rules to set to force traffic through DERP, so we can test ssh'ing to a machine through the relayed connection

TODO: test more things - see internal test plan doc
