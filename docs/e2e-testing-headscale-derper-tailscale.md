
# End to end testing: tailscale, headscale, derper


## Environment setup

For this testing, we'll use VMs on Azure.
This ensures we can test scenarios that are close to real world,
with public IP addresses and DNS names for Headscale and Derper.

This document deploys everything in the `australiaeast` region;
if you deploy in another region, substitute the name accordingly in domain names.

We'll deploy 4 VMs:

| name (same DNS name) | full domain name                             | inbound rules                                                                                           | outbound rules |
|----------------------|----------------------------------------------|---------------------------------------------------------------------------------------------------------|----------------|
| headscale            | headscale.australiaeast.cloudapp.azure.com   | - TCP 22 (ssh)<br>- TCP 80 (letsencrypt challenge)<br>- TCP 443 (headscale)                             | None           |
| derper               | derper.australiaeast.cloudapp.azure.com      | - TCP 22 (ssh)<br>- TCP 80 (derper)<br>- TCP 443 (derper)<br>- UDP 3478 (derper STUN)<br>- ICMP traffic | - ICMP traffic |
| tailscale-1          | tailscale-1.australiaeast.cloudapp.azure.com | - TCP 22 (ssh)                                                                                          | None           |
| tailscale-2          | tailscale-2.australiaeast.cloudapp.azure.com | - TCP 22 (ssh)                                                                                          | None           |

Each VM should also have the following configuration:

- OS: Ubuntu 24.04 LTS
- Architecture: x64
- Size: `DS1_v2` (1 CPU, 3.5GB RAM)
- Username: `ubuntu`
- SSH key: a public SSH key of your choosing; you'll need ssh access to all VMs

Most config can be set at VM creation time using the web UI.
The DNS name can only be set after the VM is created though.

## Setup

### Derper

```text
ssh derper.australiaeast.cloudapp.azure.com -- sudo snap install --edge derper
ssh derper.australiaeast.cloudapp.azure.com -- sudo snap set derper hostname=derper.australiaeast.cloudapp.azure.com a=:443 stun-port=3478
ssh derper.australiaeast.cloudapp.azure.com -- sudo snap restart derper
ssh derper.australiaeast.cloudapp.azure.com -- sudo snap logs derper
```

Once this is done, you should be able to visit https://derper.australiaeast.cloudapp.azure.com/ in your browser,
and see an info page including the text "This is a Tailscale DERP server".


### Headscale

```text
ssh headscale.australiaeast.cloudapp.azure.com -- sudo snap install --edge headscale

ssh headscale.australiaeast.cloudapp.azure.com -- sudo snap set headscale server-url=https://headscale.australiaeast.cloudapp.azure.com:443 listen-addr=0.0.0.0:443
# TODO: also need:
# tls_letsencrypt_hostname: "headscale.australiaeast.cloudapp.azure.com"
# derp.server.paths: ["/var/snap/headscale/common/derp.yaml"]
# see https://github.com/canonical/headscale-snap/pull/12 - we may need to update the above to supply the full custom config file

ssh headscale.australiaeast.cloudapp.azure.com -- sudo tee /var/snap/headscale/common/derp.yaml <<EOF
regions:
  900:
    regionid: 900
    regioncode: "one"
    regionname: "my first region"
    nodes:
      - name: "1"
        regionid: 900
        hostname: "derper.australiaeast.cloudapp.azure.com"
EOF

ssh headscale.australiaeast.cloudapp.azure.com -- sudo snap restart headscale
# check it's running
ssh headscale.australiaeast.cloudapp.azure.com -- sudo snap logs headscale
```

Create an initial user (tailnet) for testing:

```text
ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale users create test1
```

### Tailscale

Launch a few machines (two on azure, one locally):

```text
ssh tailscale-1.australiaeast.cloudapp.azure.com -- sudo snap install --edge tailscale
KEY="$(ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale preauthkeys create --user test1)"
ssh tailscale-1.australiaeast.cloudapp.azure.com -- sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com:443 --authkey "$KEY"
ssh tailscale-1.australiaeast.cloudapp.azure.com -- tailscale status
ssh tailscale-1.australiaeast.cloudapp.azure.com -- tailscale debug derp-map
```

```text
ssh tailscale-2.australiaeast.cloudapp.azure.com -- sudo snap install --edge tailscale
KEY="$(ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale preauthkeys create --user test1)"
ssh tailscale-2.australiaeast.cloudapp.azure.com -- sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com:443 --authkey "$KEY"
ssh tailscale-2.australiaeast.cloudapp.azure.com -- tailscale status
ssh tailscale-2.australiaeast.cloudapp.azure.com -- tailscale debug derp-map
```

```text
lxc launch ubuntu:24.04 tailscale-3 --vm -c limits.cpu=1 -c limits.memory=4GiB
lxc exec tailscale-3 -- snap install --edge tailscale
KEY="$(ssh headscale.australiaeast.cloudapp.azure.com -- sudo headscale preauthkeys create --user test1)"
lxc exec tailscale-3 -- sudo tailscale up --login-server https://headscale.australiaeast.cloudapp.azure.com:443 --authkey "$KEY"
lxc exec tailscale-3 -- tailscale status
lxc exec tailscale-3 -- tailscale debug derp-map
```


TODO: test interactive login
```text
#ssh tailscale-1.australiaeast.cloudapp.azure.com -- sudo tailscale up --login-server http://headscale.australiaeast.cloudapp.azure.com:80
```

TODO: now that the environment is set up and connected, test some more things - some ideas:
- connectivity between the tailscale machines
- connectivity between the tailscale machines with custom policies to headscale
- connectivity when relayed through the derp server
