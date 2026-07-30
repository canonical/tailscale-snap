# Copyright 2026 Canonical Ltd.

"""End-to-end tests for the Tailscale, Headscale, and DERP snaps."""

import json
import re
import time
from pathlib import Path
from subprocess import CompletedProcess

from conftest import (
    E2EContext,
    enroll_with_key,
    host_address,
    lxc_exec,
    wait_command,
    wait_tailscale,
)


def _ssh(project: str, source: str, target: str) -> CompletedProcess:
    return lxc_exec(
        project,
        source,
        [
            "ssh",
            "-B",
            "tailscale0",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=4",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            target,
            "hostname",
        ],
        check=False,
        timeout=15,
    )


def _ping(project: str, target: str, *, count: int = 3, timeout: str = "2s") -> CompletedProcess:
    return lxc_exec(
        project,
        "user-2",
        ["tailscale", "ping", f"--c={count}", f"--timeout={timeout}", target],
        check=False,
        timeout=35,
    )


def _ping_succeeded(result: CompletedProcess) -> bool:
    return bool(re.search(r"(?m)^pong from ", result.stdout))


def _wait_for_relay(project: str) -> CompletedProcess:
    deadline = time.monotonic() + 45
    result = _ping(project, "internal-1")
    while time.monotonic() < deadline:
        pongs = re.findall(r"(?m)^pong from .+$", result.stdout)
        output = result.stdout + result.stderr
        if (
            len(pongs) == 3
            and all("via DERP(one)" in pong for pong in pongs)
            and "direct connection not established" in output
        ):
            return result
        time.sleep(1)
        result = _ping(project, "internal-1")
    raise AssertionError(
        f"timed out waiting for DERP relay\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _restart_derper(project: str) -> None:
    lxc_exec(project, "derper", ["snap", "restart", "derper"])
    wait_command(
        project,
        "derper",
        [
            "curl",
            "-fsS",
            "--connect-timeout",
            "2",
            "--max-time",
            "4",
            "https://derper.e2e.test/",
        ],
        "DERP HTTPS endpoint",
    )


def _restore_derper_login(project: str, private_dir: Path) -> None:
    enroll_with_key(project, "derper", "derper", private_dir, "tag:derper")
    wait_tailscale(project, "derper")
    _restart_derper(project)


def test_custom_derp(e2e: E2EContext) -> None:
    project = e2e.project
    mapping = json.loads(lxc_exec(project, "user-2", ["tailscale", "debug", "derp-map"]).stdout)
    assert set(mapping["Regions"]) == {"900"}
    region = mapping["Regions"]["900"]
    assert any(node["HostName"] == "derper.e2e.test" for node in region["Nodes"])


def test_magicdns(e2e: E2EContext) -> None:
    project = e2e.project
    status = json.loads(lxc_exec(project, "internal-1", ["tailscale", "status", "--json"]).stdout)
    overlay_ip = next(address for address in status["TailscaleIPs"] if "." in address)
    for name in ("internal-1", "internal-1.tailnet.internal"):
        result = lxc_exec(project, "user-1", ["getent", "ahostsv4", name]).stdout
        addresses = {line.split()[0] for line in result.splitlines()}
        assert overlay_ip in addresses, f"MagicDNS did not resolve {name} to {overlay_ip}"


def test_underlay_isolation_and_overlay_ssh(e2e: E2EContext) -> None:
    project = e2e.project
    try:
        lxc_exec(project, "user-1", ["tailscale", "down"])
        underlay_ip = host_address(e2e.topology, "internal-1", "services")
        underlay = lxc_exec(
            project,
            "user-1",
            ["nc", "-z", "-w", "3", underlay_ip, "22"],
            check=False,
            timeout=10,
        )
        assert underlay.returncode != 0, "user-1 reached internal-1's services IP"
    finally:
        lxc_exec(project, "user-1", ["tailscale", "up"])
        wait_tailscale(project, "user-1")

    overlay = _ssh(project, "user-1", "internal-1")
    assert overlay.returncode == 0, overlay.stderr
    assert overlay.stdout.strip() == "internal-1"


def test_acl_and_port_rules(e2e: E2EContext) -> None:
    project = e2e.project
    allowed = _ssh(project, "user-2", "internal-1")
    assert allowed.returncode == 0, allowed.stderr
    assert allowed.stdout.strip() == "internal-1"

    for source, target in (("user-2", "user-1"), ("derper", "internal-1")):
        denied = _ssh(project, source, target)
        assert denied.returncode != 0, f"SSH {source} to {target} bypassed the ACL"
        assert "timed out" in denied.stderr.lower(), denied.stderr

    ping = _ping(project, "user-1", count=1)
    assert _ping_succeeded(ping), ping.stderr

    allowed_port = lxc_exec(
        project,
        "user-1",
        ["curl", "-sS", "-I", "--connect-timeout", "4", "http://derper:80"],
        check=False,
        timeout=10,
    )
    assert allowed_port.returncode == 0, allowed_port.stderr
    denied_port = lxc_exec(
        project,
        "user-2",
        ["curl", "-sS", "-I", "--connect-timeout", "4", "http://derper:80"],
        check=False,
        timeout=10,
    )
    assert denied_port.returncode == 28, denied_port.stderr


def test_derp_relay_and_verify_client_states(e2e: E2EContext) -> None:
    project = e2e.project
    private_dir = e2e.private_dir
    try:
        _wait_for_relay(project)
        ssh = _ssh(project, "user-2", "internal-1")
        assert ssh.returncode == 0, ssh.stderr

        lxc_exec(
            project,
            "derper",
            ["snap", "disconnect", "derper:tailscale-socket", "tailscale:socket"],
        )
        _restart_derper(project)
        ping = _ping(project, "internal-1")
        assert not _ping_succeeded(ping), "relay worked without the verifier socket"

        lxc_exec(
            project,
            "derper",
            ["snap", "connect", "derper:tailscale-socket", "tailscale:socket"],
        )
        _restart_derper(project)
        _wait_for_relay(project)

        lxc_exec(project, "derper", ["tailscale", "logout"])
        _restart_derper(project)
        ping = _ping(project, "internal-1")
        assert not _ping_succeeded(ping), "relay worked with a logged-out verifier"

        lxc_exec(project, "derper", ["snap", "set", "derper", "verify-clients=false"])
        _restart_derper(project)
        _wait_for_relay(project)
        ssh = _ssh(project, "user-2", "internal-1")
        assert ssh.returncode == 0, ssh.stderr
    finally:
        lxc_exec(
            project,
            "derper",
            ["snap", "set", "derper", "verify-clients=true"],
            check=False,
        )
        lxc_exec(
            project,
            "derper",
            ["snap", "connect", "derper:tailscale-socket", "tailscale:socket"],
            check=False,
        )
        status = lxc_exec(project, "derper", ["tailscale", "status", "--json"], check=False)
        running = False
        if status.returncode == 0:
            try:
                running = json.loads(status.stdout).get("BackendState") == "Running"
            except json.JSONDecodeError:
                pass
        if running:
            _restart_derper(project)
        else:
            _restore_derper_login(project, private_dir)
