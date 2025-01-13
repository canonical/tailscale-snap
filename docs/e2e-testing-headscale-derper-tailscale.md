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
terraform apply -var "ssh_key=YOUR PUBLIC SSH KEY CONTENTS"
```

### Deploy manually

If you aren't using Terraform, you can deploy the machines manually following the information below.

We'll deploy 5 VMs:

| name (same DNS name) | full domain name                             | inbound rules                                                                                           | outbound rules |
|----------------------|----------------------------------------------|---------------------------------------------------------------------------------------------------------|----------------|
| headscale            | headscale.australiaeast.cloudapp.azure.com   | - TCP 22 (ssh)<br>- TCP 80 (letsencrypt challenge)<br>- TCP 443 (headscale)                             | None           |
| derper               | derper.australiaeast.cloudapp.azure.com      | - TCP 22 (ssh)<br>- TCP 80 (derper)<br>- TCP 443 (derper)<br>- UDP 3478 (derper STUN)<br>- ICMP traffic | - ICMP traffic |
| tailscale-1          | tailscale-1.australiaeast.cloudapp.azure.com | - TCP 22 (ssh)                                                                                          | None           |
| tailscale-2          | tailscale-2.australiaeast.cloudapp.azure.com | - TCP 22 (ssh)                                                                                          | None           |
| tailscale-3          | tailscale-3.australiaeast.cloudapp.azure.com | - TCP 22 (ssh)                                                                                          | None           |

Each VM should also have the following configuration:

- OS: Ubuntu 24.04 LTS
- Architecture: x64
- Size: `DS1_v2` (1 CPU, 3.5GB RAM)
- Username: `ubuntu`
- SSH key: a public SSH key of your choosing; you'll need ssh access to all VMs

Most config can be set at VM creation time using the web UI.
The DNS name can only be set after the VM is created though.

## Configure services

In this step, we will install all the required software, and configure them together.

A simple diagram of how the services are connected:

```text
Headscale -----> Derper
  ^
  |
  +------------+------------+
  |            |            |
Tailscale-1  Tailscale-2  Tailscale-3
```

### Configure Derper

```bash
ssh derper.australiaeast.cloudapp.azure.com -- <<'EOF'
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
ssh headscale.australiaeast.cloudapp.azure.com -- <<'GLOBALEOF'
set -x
#sudo snap install --edge headscale
# for this testing, I've used a locally built headscale snap, from the branch at https://github.com/canonical/headscale-snap/pull/12
# rsynced to the machine.
sudo snap install --dangerous ./headscale_0.23.0_amd64.snap

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

sudo tee /var/snap/headscale/common/derp.yaml <<EOF
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
ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale users create user1
ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale users create user2
```

We'll register nodes tailscale-1 and tailscale-2 to user1,
and tailscale-3 to user2.

### Configure Tailscale

#### Configure machine tailscale-1

On tailscale-1, install Tailscale and authenticate to the Headscale server using a preauth key and user `user1`:

```bash
KEY="$(ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale preauthkeys create --user user1)"
ssh tailscale-1.australiaeast.cloudapp.azure.com -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` shows an ip address and the `user1` tailnet.
Also verify that the DERP map printed only displays a single entry: the derper we set up earlier.

Expected output:

```text
+ tailscale status
100.64.0.1      tailscale-1          user1        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```

#### Configure machine tailscale-2

On tailscale-2, install Tailscale and authenticate to the Headscale server using the default interactive login flow:

```bash
ssh tailscale-2.australiaeast.cloudapp.azure.com -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com
EOF

```

The last command should print a long url on the Headscale server domain,
and wait (it will not exit until authentication is complete.
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
ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale nodes register --user user1 --key mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b
```

This command should output:

```text
... [debug logs]
Node tailscale-2 registered
```

And the previous `tailscale up ...` command should exit with a success message:

```
+ sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com

To authenticate, visit:

        https://headscale.australiaeast.cloudapp.azure.com/register/mkey:66989ac71e017f9f0ce2a58f4b37005da55554a6bcd75c60fe4af3277bf95d4b

Success.
```

Now we can double check that Tailscale 2 is now connected to the tailnet and also has the same DERP map configuration:

```bash
ssh tailscale-2.australiaeast.cloudapp.azure.com -- <<EOF
set -x
tailscale status
tailscale debug derp-map
EOF

```

Expected output:

```text
+ tailscale status
100.64.0.2      tailscale-2          user1        linux   -
100.64.0.1      tailscale-1          user1        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```


#### Configure machine tailscale-3

On tailscale-3, install Tailscale and authenticate to the Headscale server using a preauth key with the `user2` user:

```bash
KEY="$(ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale preauthkeys create --user user2)"
ssh tailscale-3.australiaeast.cloudapp.azure.com -- <<EOF
set -x
sudo snap install --edge tailscale
sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com --authkey "$KEY"
tailscale status
tailscale debug derp-map
EOF

```

Verify that the output of `tailscale status` shows an ip address and the `user2` tailnet for `tailscale-3`.

Expected output:

```text
+ tailscale status
100.64.0.3      tailscale-3          user2        linux   -
100.64.0.2      tailscale-2          user1        linux   -
100.64.0.1      tailscale-1          user1        linux   -
+ tailscale debug derp-map
{
        "Regions": {
                                        "HostName": "derper.australiaeast.cloudapp.azure.com"
... some lines omitted, but should only be one region
```


## Testing

### MagicDNS

Verify that the Headscale MagicDNS is working:

```bash
ssh tailscale-1.australiaeast.cloudapp.azure.com -- resolvectl query --cache no --legen no tailscale-2.tailnet.internal
ssh tailscale-1.australiaeast.cloudapp.azure.com -- resolvectl query --cache no --legen no tailscale-2
```

Both should return the same ip address (within the tailnet subnet).
Expected output:

```text
tailscale-2.tailnet.internal: 100.64.0.2                    -- link: tailscale0

tailscale-2: 100.64.0.2                                     -- link: tailscale0
             (tailscale-2.tailnet.internal)
```

This verifies that the Headscale dns service and search domain is configured as expected.

---

TODO: test more things - see internal test plan doc
