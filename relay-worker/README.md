# Proteus party relay

Cloudflare Worker that connects Proteus players in party mode (one
Durable Object room per party, at most 10 members).

Cloudflare builds and deploys this folder itself from the GitHub repo
(Workers Builds, root directory `relay-worker`), on every push that
changes it. The worker's name in `wrangler.toml` must match the worker
in the Cloudflare dashboard (`claude`).

Address: `wss://claude.<subdomain>.workers.dev`. It goes into the
`RELAY_URL` repository secret, which the Release workflow builds into
Proteus. Setup steps: ../SAJAT_VERZIO.md
