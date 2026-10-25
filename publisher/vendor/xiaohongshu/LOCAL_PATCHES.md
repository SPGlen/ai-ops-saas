# Local modifications to xiaohongshu-mcp

Upstream: https://github.com/xpzouying/xiaohongshu-mcp
Pinned commit: 7797fd375aba02dcd33afe143f6bee13e5870859
License: Apache-2.0 (original LICENSE retained).
Modified for Zhiying AI Ops on 2026-10-21. SOURCE.json records the original input hashes. LOCAL_PATCHES.json lists local file changes and current hashes. Source files without substantive edits preserve their original bytes. Modified Go files carry a change notice.

- Require a strong bearer token and bind the upstream process to loopback.
- Require an absolute, per-account cookies path; never use a shared cookies.json fallback.
- Use managed standard Chromium with its sandbox enabled. Do not download the upstream custom browser or enable fingerprint/stealth changes.
- Return structured account identity with login status for account-bound verification.
- Upgrade the MCP Go SDK and affected dependencies; exact versions and integrity hashes are in go.mod/go.sum.

Account processes, credentials, temporary profiles and encrypted state are managed by the surrounding publisher. MCP handshake and source tests are separate from real account acceptance. Go reachability scans have zero reachable findings but retain module-only advisory GO-2026-5932; see docs/ACCEPTANCE.md.
