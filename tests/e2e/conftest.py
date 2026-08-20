# Copyright 2026 Canonical Ltd.

"""Pytest setup for the local Headscale, DERP, and Tailscale topology."""

import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

E2E_DIR = Path(__file__).resolve().parent
ROOT_DIR = E2E_DIR.parent.parent
CONFIG_DIR = E2E_DIR / "config"
HOSTS = ("headscale", "derper", "internal-1", "user-1", "user-2")
TAILSCALE_HOSTS = ("derper", "internal-1", "user-1", "user-2")
PRODUCTS = {
    "headscale": ("headscale",),
    "derper": ("derper", "tailscale"),
    "internal-1": ("tailscale",),
    "user-1": ("tailscale",),
    "user-2": ("tailscale",),
}
KEEP_ENV = os.environ.get("KEEP_ENV") == "1"
REUSE_ENV = os.environ.get("REUSE_ENV") == "1"


@dataclass
class TFContext:
    project: str
    topology: dict[str, Any]


@dataclass
class E2EContext(TFContext):
    private_dir: Path


@dataclass
class SnapArtifact:
    path: str
    channel: str | None = None


def run(
    command: list[str], *, check: bool = True, timeout: int = 300
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [str(part) for part in command],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        cmd = " ".join(str(part) for part in command)
        raise RuntimeError(f"command failed ({result.returncode}): {cmd}\n{result.stderr}")
    return result


def lxc_exec(
    project: str,
    host: str,
    command: list[str],
    *,
    check: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    return run(
        ["lxc", "--project", project, "exec", f"local:{host}", "--", *command],
        check=check,
        timeout=timeout,
    )


def shell(
    project: str, host: str, script: str, *, check: bool = True
) -> subprocess.CompletedProcess:
    return lxc_exec(project, host, ["sh", "-eu", "-c", script], check=check)


def push(project: str, host: str, source: str, destination: str, mode: str) -> None:
    run(
        [
            "lxc",
            "--project",
            project,
            "file",
            "push",
            source,
            f"local:{host}{destination}",
        ]
    )
    lxc_exec(project, host, ["chown", "root:root", destination])
    lxc_exec(project, host, ["chmod", mode, destination])


def write_remote(
    project: str,
    host: str,
    destination: str,
    content: str,
    private_dir: Path,
    mode: str = "0644",
) -> None:
    with tempfile.NamedTemporaryFile("w", dir=private_dir, delete=False) as stream:
        stream.write(content)
        temporary = stream.name
    try:
        push(project, host, temporary, destination, mode)
    finally:
        Path(temporary).unlink(missing_ok=True)


def host_address(topology: dict[str, Any], host: str, network: str) -> str:
    for nic in topology["hosts"][host]["nics"].values():
        if nic["network"] == network:
            return nic["address"]
    raise AssertionError(f"{host} has no address on {network}")


def wait_command(
    project: str, host: str, command: list[str], description: str, *, timeout: int = 120
) -> subprocess.CompletedProcess:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = lxc_exec(project, host, command, check=False)
        if result.returncode == 0:
            return result
        time.sleep(2)
    raise AssertionError(f"timed out waiting for {description}")


def wait_tailscale(project: str, host: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = lxc_exec(project, host, ["tailscale", "status", "--json"], check=False)
        if result.returncode == 0 and json.loads(result.stdout).get("BackendState") == "Running":
            return
        time.sleep(2)
    raise AssertionError(f"timed out waiting for Tailscale Running on {host}")


def install_snaps(project: str, artifacts: dict[str, SnapArtifact]) -> None:
    for host, products in PRODUCTS.items():
        for product in products:
            artifact = artifacts[product]
            if artifact.channel is None:
                remote_snap = f"/tmp/{product}"
                push(project, host, artifact.path, remote_snap, "0600")
                try:
                    lxc_exec(project, host, ["snap", "install", "--dangerous", remote_snap])
                finally:
                    lxc_exec(project, host, ["rm", "-f", remote_snap], check=False)
            else:
                lxc_exec(
                    project,
                    host,
                    ["snap", "install", artifact.path, f"--channel={artifact.channel}"],
                )

    for host in TAILSCALE_HOSTS:
        for plug in (
            "firewall-control",
            "network-control",
            "sys-devices-virtual-dmi-ids",
        ):
            lxc_exec(project, host, ["snap", "connect", f"tailscale:{plug}"])
        # The daemon may exhaust its start limit before its privileged plugs are connected.
        lxc_exec(
            project,
            host,
            ["systemctl", "reset-failed", "snap.tailscale.tailscaled.service"],
        )
        lxc_exec(project, host, ["snap", "restart", "tailscale"])

    lxc_exec(
        project,
        "derper",
        ["snap", "connect", "derper:tailscale-socket", "tailscale:socket"],
    )


def configure_certificates(project: str, private_dir: Path) -> None:
    ca_key_path = private_dir / "ca.key"
    ca_cert_path = private_dir / "ca.crt"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            "/CN=Tailscale snap E2E CA",
            "-keyout",
            str(ca_key_path),
            "-out",
            str(ca_cert_path),
        ]
    )
    for hostname in ("headscale.e2e.test", "derper.e2e.test"):
        key_path = private_dir / f"{hostname}.key"
        request_path = private_dir / f"{hostname}.csr"
        cert_path = private_dir / f"{hostname}.crt"
        extension_path = private_dir / f"{hostname}.ext"
        extension_path.write_text(
            f"subjectAltName=DNS:{hostname}\nextendedKeyUsage=serverAuth\n",
            encoding="ascii",
        )
        run(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                f"/CN={hostname}",
                "-keyout",
                str(key_path),
                "-out",
                str(request_path),
            ]
        )
        run(
            [
                "openssl",
                "x509",
                "-req",
                "-days",
                "2",
                "-in",
                str(request_path),
                "-CA",
                str(ca_cert_path),
                "-CAkey",
                str(ca_key_path),
                "-CAcreateserial",
                "-extfile",
                str(extension_path),
                "-out",
                str(cert_path),
            ]
        )

    for host in HOSTS:
        push(
            project,
            host,
            str(ca_cert_path),
            "/usr/local/share/ca-certificates/e2e-ca.crt",
            "0644",
        )
        lxc_exec(project, host, ["update-ca-certificates"])

    for host in TAILSCALE_HOSTS:
        lxc_exec(project, host, ["snap", "restart", "tailscale"])

    lxc_exec(project, "headscale", ["mkdir", "-p", "/var/snap/headscale/common"])
    push(
        project,
        "headscale",
        str(private_dir / "headscale.e2e.test.crt"),
        "/var/snap/headscale/common/headscale.crt",
        "0644",
    )
    push(
        project,
        "headscale",
        str(private_dir / "headscale.e2e.test.key"),
        "/var/snap/headscale/common/headscale.key",
        "0600",
    )
    lxc_exec(project, "derper", ["mkdir", "-p", "/var/snap/derper/common/certs"])
    push(
        project,
        "derper",
        str(private_dir / "derper.e2e.test.crt"),
        "/var/snap/derper/common/certs/derper.e2e.test.crt",
        "0644",
    )
    push(
        project,
        "derper",
        str(private_dir / "derper.e2e.test.key"),
        "/var/snap/derper/common/certs/derper.e2e.test.key",
        "0600",
    )


def configure_hosts(project: str, topology: dict[str, Any], private_dir: Path) -> None:
    for host in HOSTS:
        network = "users" if host.startswith("user-") else "services"
        content = (
            "127.0.0.1 localhost\n"
            f"{host_address(topology, 'headscale', network)} headscale.e2e.test\n"
            f"{host_address(topology, 'derper', network)} derper.e2e.test\n"
        )
        write_remote(project, host, "/etc/hosts", content, private_dir)


def configure_services(project: str) -> None:
    lxc_exec(project, "headscale", ["mkdir", "-p", "/var/snap/headscale/common/internal"])
    for source, destination in (
        ("headscale.yaml", "/var/snap/headscale/common/config.yaml"),
        ("derp.yaml", "/var/snap/headscale/common/derp.yaml"),
        ("policy.hujson", "/var/snap/headscale/common/policies.hujson"),
    ):
        push(project, "headscale", str(CONFIG_DIR / source), destination, "0644")

    lxc_exec(project, "headscale", ["snap", "restart", "headscale"])
    wait_command(
        project,
        "headscale",
        ["curl", "-fsS", "https://headscale.e2e.test/health"],
        "Headscale HTTPS endpoint",
    )

    lxc_exec(
        project,
        "derper",
        [
            "snap",
            "set",
            "derper",
            "hostname=derper.e2e.test",
            "certmode=manual",
            "certdir=certs",
            "verify-clients=true",
        ],
    )
    lxc_exec(project, "derper", ["snap", "restart", "derper"])
    wait_command(
        project,
        "derper",
        ["curl", "-fsS", "https://derper.e2e.test/"],
        "DERP HTTPS endpoint",
    )


def preauth_key(project: str, user: str) -> str:
    users = json.loads(
        lxc_exec(project, "headscale", ["headscale", "users", "list", "-o", "json"]).stdout
    )
    matches = [entry["id"] for entry in users if entry.get("name") == user]
    if len(matches) != 1:
        raise AssertionError(f"expected one Headscale user named {user}")
    try:
        user_id = str(int(matches[0]))
    except (TypeError, ValueError) as error:
        raise AssertionError(f"Headscale returned an invalid ID for user {user}") from error

    payload = json.loads(
        lxc_exec(
            project,
            "headscale",
            [
                "headscale",
                "preauthkeys",
                "create",
                "--user",
                user_id,
                "--expiration",
                "1h",
                "-o",
                "json",
            ],
        ).stdout
    )
    key = payload.get("key")
    if not isinstance(key, str) or not key:
        raise AssertionError(f"Headscale did not return a preauth key for {user}")
    return key


def enroll_with_key(
    project: str, host: str, user: str, private_dir: Path, tag: str | None = None
) -> None:
    secret_path = "/run/e2e-authkey"
    write_remote(
        project,
        host,
        secret_path,
        preauth_key(project, user) + "\n",
        private_dir,
        "0600",
    )
    options = f" --advertise-tags={tag}" if tag else ""
    try:
        shell(
            project,
            host,
            "tailscale up --login-server=https://headscale.e2e.test "
            ' --authkey="$(cat /run/e2e-authkey)"' + options,
        )
    finally:
        lxc_exec(project, host, ["rm", "-f", secret_path], check=False)


def registration_key(status: str) -> str | None:
    try:
        auth_url = json.loads(status).get("AuthURL")
    except json.JSONDecodeError:
        return None
    if not isinstance(auth_url, str):
        return None
    match = re.fullmatch(r"https://headscale\.e2e\.test/register/([A-Za-z0-9_-]+)", auth_url)
    return match.group(1) if match else None


def enroll_user2(project: str, private_dir: Path) -> None:
    exit_path = "/run/e2e-user2-exit"
    try:
        shell(
            project,
            "user-2",
            "umask 077; rm -f /run/e2e-user2-exit; "
            "nohup sh -c 'tailscale up --login-server=https://headscale.e2e.test; "
            'status=$?; printf "%s" "$status" >/run/e2e-user2-exit\' '
            "</dev/null >/dev/null 2>&1 &",
        )

        deadline = time.monotonic() + 120
        registration = None
        while time.monotonic() < deadline:
            result = lxc_exec(project, "user-2", ["tailscale", "status", "--json"], check=False)
            if result.returncode == 0:
                registration = registration_key(result.stdout)
                if registration:
                    break
            time.sleep(2)
        if registration is None:
            raise AssertionError("timed out waiting for user-2 registration URL")

        secret_path = "/run/e2e-register-key"
        write_remote(project, "headscale", secret_path, registration + "\n", private_dir, "0600")
        try:
            shell(
                project,
                "headscale",
                'headscale nodes register --user user2 --key "$(cat /run/e2e-register-key)"',
            )
        finally:
            lxc_exec(project, "headscale", ["rm", "-f", secret_path], check=False)

        wait_command(
            project,
            "user-2",
            ["test", "-s", exit_path],
            "user-2 tailscale up exit status",
        )
        status = lxc_exec(project, "user-2", ["cat", exit_path]).stdout.strip()
        if status != "0":
            raise AssertionError("interactive user-2 enrollment failed")
    finally:
        lxc_exec(project, "user-2", ["rm", "-f", exit_path], check=False)


def configure_tailnet(project: str, private_dir: Path) -> None:
    for user in ("derper", "internal", "user1", "user2"):
        lxc_exec(project, "headscale", ["headscale", "users", "create", user])

    enroll_with_key(project, "derper", "derper", private_dir, "tag:derper")
    enroll_with_key(project, "internal-1", "internal", private_dir, "tag:internal")
    enroll_with_key(project, "user-1", "user1", private_dir)
    enroll_user2(project, private_dir)
    for host in TAILSCALE_HOSTS:
        wait_tailscale(project, host)


def configure_ssh(project: str, private_dir: Path) -> None:
    key_path = private_dir / "id_ed25519"
    run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "tailscale-e2e",
            "-f",
            str(key_path),
        ]
    )
    public = Path(f"{key_path}.pub")
    for host in TAILSCALE_HOSTS:
        lxc_exec(project, host, ["mkdir", "-p", "/root/.ssh"])
        lxc_exec(project, host, ["chmod", "0700", "/root/.ssh"])
        push(project, host, str(key_path), "/root/.ssh/id_ed25519", "0600")
        push(project, host, str(public), "/root/.ssh/authorized_keys", "0600")


def get_snap_artifact(snap: str) -> SnapArtifact:
    path_from_env = os.environ.get(f"{snap.upper()}_TEST_SNAP")
    if path_from_env:
        if not Path(path_from_env).is_absolute():
            pytest.fail(f"{snap.upper()}_TEST_SNAP env variable is not set to an absolute path")
        return SnapArtifact(path=path_from_env)

    manifest = yaml.safe_load((ROOT_DIR / "snap/snapcraft.yaml").read_text())
    local_snap_name = manifest.get("name") if isinstance(manifest, dict) else None
    if not isinstance(local_snap_name, str):
        pytest.fail("snap/snapcraft.yaml has no name field")

    if snap != local_snap_name:
        return SnapArtifact(path=snap, channel="latest/edge")

    snaps = list(ROOT_DIR.glob(f"{snap}_*.snap"))
    if len(snaps) != 1:
        pytest.fail(f"Expected exactly one {snap}_*.snap artifact, found {len(snaps)}")
    return SnapArtifact(path=str(snaps[0]))


@pytest.fixture(scope="session")
def artifacts() -> Generator[dict[str, SnapArtifact], None, None]:
    derper = get_snap_artifact("derper")
    tailscale = get_snap_artifact("tailscale")
    headscale = get_snap_artifact("headscale")

    yield {
        "derper": derper,
        "tailscale": tailscale,
        "headscale": headscale,
    }


@pytest.fixture(scope="session")
def terraform(artifacts: dict[str, SnapArtifact]) -> Generator[TFContext, None, None]:
    if REUSE_ENV and not KEEP_ENV:
        pytest.fail("REUSE_ENV=1 requires KEEP_ENV=1 to preserve the existing environment")

    terraform_dir = ROOT_DIR / ".terraform/e2e"
    terraform_state_path = terraform_dir / "terraform.tfstate"
    terraform_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TF_DATA_DIR"] = str(terraform_dir / "data")

    run(["terraform", f"-chdir={E2E_DIR}", "init", f"-backend-config=path={terraform_state_path}"])
    if not REUSE_ENV:
        run(["terraform", f"-chdir={E2E_DIR}", "apply", "-auto-approve"], timeout=600)

    topology: dict[str, Any] = json.loads(
        run(["terraform", f"-chdir={E2E_DIR}", "output", "-json", "topology"]).stdout
    )
    if not isinstance(topology, dict) or not set(HOSTS) <= set(topology.get("hosts", {})):
        pytest.fail("Terraform topology is missing required hosts")
    project: str = topology.get("project_name", "")
    if not project:
        pytest.fail("Terraform topology is missing project_name")

    try:
        yield TFContext(project=project, topology=topology)
    finally:
        if not KEEP_ENV:
            run(["terraform", f"-chdir={E2E_DIR}", "destroy", "-auto-approve"])


@pytest.fixture(scope="session")
def e2e(
    terraform: TFContext, artifacts: dict[str, SnapArtifact]
) -> Generator[E2EContext, None, None]:
    with tempfile.TemporaryDirectory(prefix="tailscale-snap-e2e-") as temporary:
        private_dir = Path(temporary)
        private_dir.chmod(0o700)
        if not REUSE_ENV:
            install_snaps(terraform.project, artifacts)
            configure_certificates(terraform.project, private_dir)
            configure_hosts(terraform.project, terraform.topology, private_dir)
            configure_services(terraform.project)
            configure_tailnet(terraform.project, private_dir)
            configure_ssh(terraform.project, private_dir)
        yield E2EContext(
            project=terraform.project,
            topology=terraform.topology,
            private_dir=private_dir,
        )
