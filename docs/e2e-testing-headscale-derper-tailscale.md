
# End to end testing: tailscale, headscale, derper


## Environment setup

TODO: clean this section up

Azure

in `australiaeast` region.

VM1
- name: headscale
- ubuntu 24.04
- x64
- DS1_v2 (1 cpu, 3.5G memory)
- username: ubuntu
- add your ssh public key
- allow inbound ports:
  - 22 (ssh)
  - 80 (for letsencrypt challenge when headscale generates certs)
  - 443 (for headscale)

After deployment, navigate to the headscale VM and add a dns name (`headscale`). This will make the VM accessible via `headscale.australiaeast.cloudapp.azure.com`.

VM2
- name: derper
- ubuntu 24.04
- x64
- DS1_v2 (1 cpu, 3.5G memory)
- username: ubuntu
- add your ssh public key
- allow inbound ports (see https://tailscale.com/kb/1118/custom-derp-servers#required-ports ):
  - TCP 22 (ssh)
  - UDP 3478 (for derper stun port)
  - TCP 443 (for derper https listen address)
  - TCP 80 (for derper http listen address)
  - inbound and outbound ICMP traffic

NOTE: azure web UI wouldn't let me create a rule for ICMP type traffic (it ignored that I'd checked ICMPv4), so I just opened it up to accept any protocol on any port inbound and outbound for now...

VM3
- name: tailscale-1
- ubuntu 24.04
- x64
- DS1_v2 (1 cpu, 3.5G memory)
- username: ubuntu
- add your ssh public key
- allow inbound ports:
  - 22 (ssh)

After deployment, navigate to the tailscale-1 VM and add a dns name (`tailscale-1`). This will make the VM accessible via `tailscale-1.australiaeast.cloudapp.azure.com`.

Create another VM identical to the above, but name it `tailscale-2`, and use `tailscale-2` for the dns name.

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
