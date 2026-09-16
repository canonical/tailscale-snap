# Copyright 2026 Canonical Ltd.

"""Checks for the Headscale configuration overlay merge."""

import yaml
from conftest import CONFIG_DIR, deep_merge


def test_nested_dicts_merge_without_dropping_siblings():
    base = {"derp": {"server": {"enabled": False}, "auto_update_enabled": True}}
    deep_merge(base, {"derp": {"paths": ["/derp.yaml"]}})
    assert base == {
        "derp": {
            "server": {"enabled": False},
            "auto_update_enabled": True,
            "paths": ["/derp.yaml"],
        }
    }


def test_lists_are_replaced_not_appended():
    # derp.urls relies on this: the upstream DERP map must be cleared, not extended.
    base = {"derp": {"urls": ["https://controlplane.tailscale.com/derpmap/default"]}}
    deep_merge(base, {"derp": {"urls": []}})
    assert base["derp"]["urls"] == []


def test_scalar_is_replaced_and_new_key_is_added():
    base = {"disable_check_updates": False}
    deep_merge(base, {"disable_check_updates": True, "tls_cert_path": "/headscale.crt"})
    assert base == {"disable_check_updates": True, "tls_cert_path": "/headscale.crt"}


def test_base_keys_absent_from_overlay_survive():
    # The point of the overlay: version-specific keys we never touch stay intact.
    base = {"node": {"ephemeral": {"inactivity_timeout": "30m"}}, "listen_addr": "127.0.0.1:8080"}
    deep_merge(base, {"listen_addr": "0.0.0.0:443"})
    assert base["node"] == {"ephemeral": {"inactivity_timeout": "30m"}}
    assert base["listen_addr"] == "0.0.0.0:443"


def test_overrides_file_is_a_yaml_mapping():
    # Fails here in seconds rather than minutes into a provisioned e2e run.
    overrides = yaml.safe_load((CONFIG_DIR / "headscale-overrides.yaml").read_text())
    assert isinstance(overrides, dict)
    assert overrides["server_url"] == "https://headscale.e2e.test"
