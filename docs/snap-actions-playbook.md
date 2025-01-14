# Snap actions playbook

This document describes how to interact with the Tailscale snap itself for performing various tasks.

## How to view the service logs

The logs can be viewed through `snap logs`:

```bash
sudo snap logs tailscale
```

For more lines:

```bash
sudo snap logs -n 100 tailscale
```

## How to manage the Tailscale service

To stop the Tailscale service:

```console
$ sudo snap stop tailscale
Stopped.
```

While the service is stopped, the `tailscale` client command is expected to fail with the following message:

```console
$ tailscale status
failed to connect to local tailscaled; it doesn't appear to be running (sudo systemctl start tailscaled ?)
```

To start the Tailscale service again:

```console
$ sudo snap start tailscale
Started.
```

The `tailscale` client command should be working again.

The service can also be restarted in a single command:

```console
$ sudo snap restart tailscale
Restarted.
```

Stopping and starting or restarting the Tailscale service should *not* result in needing to re-login.

## How to update Tailscale

To update Tailscale on a machine, refresh through snap:

```console
$ sudo snap refresh tailscale
tailscale ... refreshed
```

The Tailscale service will *not* automatically restart;
the previous revision will continue to run.
Restarting the Tailscale service may result in interrupted network connections.

When you are ready, you can restart the Tailscale service,
so that it will be now running the new revision:

```console
$ sudo snap restart tailscale
Restarted.
```

