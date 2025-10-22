## New Tailscale Release Available

A new version of Tailscale has been released upstream.

**Current snap version:** `{{CURRENT_VERSION}}`
**Latest upstream version:** `{{LATEST_VERSION}}`
**Release date:** {{RELEASE_DATE}}

### Upstream Release Information

:link: [View release on GitHub]({{RELEASE_URL}})

### Release Notes

<details>
<summary>Click to expand release notes</summary>

{{RELEASE_NOTES}}

</details>

### Next Steps

1. Review the release notes above
2. Update the version in `snap/snapcraft.yaml` from `{{CURRENT_VERSION}}` to `{{LATEST_VERSION}}`
3. Create a PR titled "Bump to {{LATEST_VERSION}}"
4. Merge PR (automatically publishes to `latest/edge`)
5. Test the snap from edge channel
6. Promote to candidate/ stable channel if needed

---
*This issue was automatically created by the [check-upstream-release workflow](https://github.com/{{REPOSITORY}}/actions/workflows/check-upstream-release.yaml)*
