# Local end-to-end testing

The `e2e` tox target tests locally built Tailscale, Headscale, and Derper
snaps in an isolated LXD environment.

This is a developer test. It is not a replacement for the
[Azure test procedure](./e2e-testing-headscale-derper-tailscale.md)
or production qualification.

## Prerequisites

The host must provide:

- Linux with a working local LXD installation and access to its socket
- a `default` LXD storage pool and the `ubuntu:24.04` image remote
- Terraform 1.5 or later
- tox, uv, OpenSSL, and OpenSSH client tools
- internet access for the Ubuntu image and package installation
- enough capacity for five LXD containers

Place exactly one artifact matching each pattern in the repository root:

```text
tailscale_*.snap
headscale_*.snap
derper_*.snap
```

The target does not build these artifacts. Build or obtain them before
running the test. Duplicate matching files also cause the target to fail.

## Run the test

From the repository root:

```bash
tox -e e2e
```

The target initializes Terraform, creates the LXD environment, installs the
three candidate snaps, runs the tests, and destroys the environment. Cleanup
runs after both success and failure.

To retain the environment for inspection:

```bash
KEEP_ENV=1 tox -e e2e
```

List the retained containers with:

```bash
lxc list --project tailscale-e2e
```

To rerun tests without reinstalling or reconfiguring the snaps:

```bash
KEEP_ENV=1 REUSE_ENV=1 tox -e e2e
```

`REUSE_ENV=1` is only for debugging. It skips provisioning and can hide setup
failures or reuse state left by an interrupted test. The three snap artifacts
are still required because the tox runner validates them before pytest starts.

## Cleanup

The runner keeps Terraform data outside `tests/e2e`. Use the same data
directory when destroying a retained environment:

```bash
TF_DATA_DIR=.terraform/e2e/data \
  terraform -chdir=tests/e2e destroy -auto-approve
```

Running `terraform -chdir=tests/e2e destroy` without `TF_DATA_DIR` uses a
different backend and fails with `Backend initialization required`.

If the backend metadata is missing, reinitialize it before cleanup:

```bash
TF_DATA_DIR=.terraform/e2e/data \
  terraform -chdir=tests/e2e init -reconfigure \
  -backend-config="path=$(pwd)/.terraform/e2e/terraform.tfstate"

TF_DATA_DIR=.terraform/e2e/data \
  terraform -chdir=tests/e2e destroy -auto-approve
```

After an interrupted run, destroying and recreating the environment is safer
than assuming its Headscale, Derper, or Tailscale state was restored.

## What the test does

Terraform creates five containers in the fixed `tailscale-e2e` LXD project:

- `headscale`
- `derper`
- `internal-1`
- `user-1`
- `user-2`

The environment uses separate services and users networks. Cross-network
underlay traffic is rejected, IPv6 is disabled, and Headscale and Derper are
attached to both networks. This prevents a direct peer path and forces traffic
between users and internal services through the custom DERP server.

The fixture:

- installs all three candidate snaps with `--dangerous`
- connects interfaces required by dangerous snap installation
- creates a local certificate authority and manual TLS certificates
- configures Headscale with MagicDNS, a policy, and one custom DERP region
- enrolls three Tailscale nodes with pre-authentication keys
- enrolls `user-2` through Headscale's interactive registration flow
- configures SSH keys used for connectivity checks

The tests verify:

- the custom DERP map reaches a Tailscale client
- MagicDNS resolves short and fully qualified names to the overlay address
- the underlay is isolated while overlay SSH works
- representative allow, deny, ICMP, and port-based ACL behavior
- sustained relay through the custom DERP without a direct upgrade
- `verify-clients=true` fails closed when the verifier socket is disconnected
- `verify-clients=true` fails closed when the local Tailscale verifier is logged out
- `verify-clients=false` permits relay without an authenticated verifier

## What the test does not do

The local suite does not test:

- public DNS, public IP addresses, or internet ingress
- ACME certificate issuance or renewal
- real NAT traversal or direct WireGuard peer paths
- IPv6 connectivity
- Snap Store assertions, review, or interface auto-connection
- snap refreshes, upgrades, rollbacks, or data migration
- every Headscale ACL edge or every Tailscale command
- performance, scale, long-running stability, or resource consumption
- production hardening or security boundaries outside snap confinement
- architectures other than those represented by the supplied artifacts

LXD containers share the host kernel. Results do not prove equivalent behavior
on VMs, public clouds, or different kernels. Headscale and Derper are also test
artifacts, so a failure does not by itself identify which snap is defective.

The project and network names are fixed. Do not run this suite concurrently on
the same LXD host.
