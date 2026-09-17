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

Build the local snap under test and place exactly one matching artifact in the
repository root:

```text
tailscale_*.snap
```

Headscale and Derper install from `latest/edge`.

Each snap's source can be overridden with environment variables. For `TAILSCALE`,
`HEADSCALE`, and `DERPER`:

| Variable | Effect | Precedence |
|----------|--------|------------|
| `<SNAP>_TEST_SNAP` | Install this local artifact (must be an absolute path). | 1 (highest) |
| `<SNAP>_TEST_CHANNEL` | Install from this snap channel. | 2 |
| neither | Tailscale: the `tailscale_*.snap` in the repository root. Headscale and Derper: `latest/edge`. | 3 |

For example, to run the test against Headscale in an older track:

```bash
HEADSCALE_TEST_CHANNEL=0.26/stable tox -e e2e
```

Setting `TAILSCALE_TEST_CHANNEL` installs the published Tailscale snap and skips
the repository-root artifact entirely.

## Run the test

From the repository root:

```bash
tox -e e2e
```

The target initializes Terraform, creates the LXD environment, installs the
local candidate snap and Headscale and Derper from `latest/edge`, runs the
tests, and destroys the environment. Cleanup runs after both success and failure.

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
failures or reuse state left by an interrupted test.

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

## Running the workflow with non-default snaps

The `End-to-end tests` workflow can be dispatched manually. All six inputs are
optional, and a dispatch with none of them set behaves exactly as a pull request
run does.

| Input | Effect | Default |
|-------|--------|---------|
| `tailscale-channel` | Install Tailscale from this snap channel instead of building it | build the current checkout |
| `tailscale-branch` | Build Tailscale from this ref of `canonical/tailscale-snap` | build the current checkout |
| `headscale-channel` | Install Headscale from this snap channel | `latest/edge` |
| `headscale-branch` | Build Headscale from this ref of `canonical/headscale-snap` | `latest/edge` |
| `derper-channel` | Install Derper from this snap channel | `latest/edge` |
| `derper-branch` | Build Derper from this ref of `canonical/derper-snap` | `latest/edge` |

Setting both a channel and a branch for the same snap fails the run immediately.

A `*-branch` input also accepts a tag or a commit SHA; it is passed straight to `actions/checkout`.

### Headscale configuration across versions

The Headscale snap's install hook writes a `config.yaml` matching the Headscale
version it ships. The suite does not replace that file, instead, it deep-merges
`tests/e2e/config/headscale-overrides.yaml` over it, so keys the suite does not
care about keep whatever the installed version considers correct. This is an attempt
to make `headscale-channel` and `headscale-branch` usable across releases that
move configuration keys.

Keep the overrides file minimal. Every key in it is a key an upstream release
can rename or relocate. Do not restate values the snap's own default already
gets right.

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

- installs the local candidate snap with `--dangerous` and Headscale and Derper from `latest/edge`
- connects interfaces required by dangerous snap installation
- creates a local certificate authority and manual TLS certificates
- configures Headscale by merging `tests/e2e/config/headscale-overrides.yaml` over
  the configuration the Headscale snap installed itself, then adds a policy and
  one custom DERP region
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
