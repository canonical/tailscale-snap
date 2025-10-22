# Automated Upstream Release Tracking

## Overview

The repository includes an automated workflow that monitors the upstream Tailscale repository for new releases and creates GitHub issues when updates are available.

## How It Works

The workflow:

1. Reads the current version from `snap/snapcraft.yaml`
2. Fetches the latest Tailscale release from https://github.com/tailscale/tailscale
3. Compares versions
4. Creates an issue if a new version is detected (prevents duplicates)

## Schedule

Runs **weekly on Mondays at 12:00 AM UTC**.

## Manual Trigger

To run the workflow manually:

1. Go to [Actions tab](https://github.com/canonical/tailscale-snap/actions/workflows/check-upstream-release.yaml)
2. Click "Run workflow"
3. Select the branch and click "Run workflow"

## Created Issues

When a new release is detected, an issue is created with:

- **Title**: `Bump to Tailscale X.Y.Z`
- **Labels**: `upstream-release`, `version-bump`
- **Content**:
  - Current and latest version info
  - Link to upstream release notes
  - Task checklist for version bump

## Version Bump Process

When an issue is created:

1. Review the release notes
2. Update version in `snap/snapcraft.yaml`
3. Create PR titled "Bump to X.Y.Z"
4. Merge PR (automatically publishes to `latest/edge` channel)
5. Test the snap from edge channel
6. Promote to stable if tests pass

## Files

- **Workflow**: `.github/workflows/check-upstream-release.yaml`
- **Issue Template**: `.github/ISSUE_TEMPLATE/upstream-release-issue.md`

You can customize the format of created issues by editing the template file. The template uses placeholders like `{{CURRENT_VERSION}}` and `{{LATEST_VERSION}}` that are automatically replaced with actual values.
