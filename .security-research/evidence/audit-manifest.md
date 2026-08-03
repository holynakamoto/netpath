# Audit Manifest — WordPress Core Security Audit Lab

- Generated: 2026-07-20
- Lab root: /Users/nickmoore/netpath/.security-research/wordpress-develop
- Evidence: /Users/nickmoore/netpath/.security-research/evidence
- Disclosure route: https://hackerone.com/wordpress
- Official guidance: https://make.wordpress.org/core/handbook/testing/reporting-security-vulnerabilities/
- AI assistance: Hermes (Codex-class) assisted source analysis & report drafting; the human
  researcher manually validates every finding, reproduces locally, and submits. AI assistance
  is disclosed in any HackerOne report.

## Environment (exact versions recorded at setup)
- Host: macOS (user nickmoore), Darwin arm64
- Git: 2.50.1 (Apple Git-155)
- Docker: 29.6.1 (Client + Engine), Docker Desktop 4.80.0 (232116)
- Node.js: v26.5.0   ⚠️ PRD targets 20.x — DEVIATION (see Notes)
- npm: 11.17.0        ⚠️ PRD targets 10.x — DEVIATION (see Notes)
- PHP (in container): 8.3.32
- Database (in container): MariaDB 11.8.6 (image resolved to mariadb; compose var LOCAL_DB_TYPE)
- WP-CLI (in container): 2.12.0
- WordPress Core (installed): 7.1-beta2-62791-src   (trunk, /src build — source-review friendly)
- Container platform note: images are linux/amd64 and run under emulation on the arm64 host
  (Docker Desktop Rosetta/QEMU). `npm run test:php` prints a platform-mismatch warning but
  passes. Recorded for reproducibility on Apple Silicon.

## Source revision (trunk)
- Commit: d792cbd66941a708d62b1778f044393206b95c63
- HEAD message: "General: Make sure `get_file_data()` recognizes headers prefixed by a `<?` tag."
- Branch: trunk (working tree clean, up to date with origin/trunk)
- Remote: https://github.com/WordPress/wordpress-develop
- Clone depth: 1 (use `git fetch --unshallow` for fix/diff analysis later)
- Repo dependencies: node_modules installed from lockfile (npm install already present); build:dev run.

## Container configuration
- Tool: @wordpress/env (wp-env) via `tools/local-env` + generated `docker-compose.yml`
- Network: `wpdevnet` (bridge, local only)
- Services:
  - wordpress-develop  (nginx:alpine)  — :8889 -> 80   [web]
  - php                (wordpressdevelop/php:latest) — PHP 8.3.32 (php-fpm)
  - mysql             (mariadb:latest)  — internal :3306; root password `password` (local-only)
  - cli               (wordpressdevelop/cli:latest) — WP-CLI 2.12.0
  - memcached         (optional, off unless LOCAL_PHP_MEMCACHED=true)
- Volume: `./` (repo) mounted read-write at `/var/www` in php/cli/web containers
- Local endpoint: http://localhost:8889
- WP_DEBUG / WP_DEBUG_LOG / WP_DEBUG_DISPLAY / SCRIPT_DEBUG = true; WP_ENVIRONMENT_TYPE=local;
  WP_DEVELOPMENT_MODE=core
- Default lab admin credentials (LOCAL-ONLY test): admin / password

## Verification checklist (PRD §4.4) — ALL PASS 2026-07-20
- [x] Docker containers running / healthy enough to serve
      -> wordpress-develop (Up), php (Up), mysql (Up, healthy), cli (Up)
- [x] http://localhost:8889/ returns a successful WordPress response
      -> `curl -o /dev/null -w '%{http_code}'` = 200
- [x] http://localhost:8889/wp-json/ returns valid REST API JSON
      -> JSON with "name":"WordPress Develop", "url":"http://localhost:8889"
- [x] Administrator login works locally
      -> `wp-login.php` POST (admin/password) -> 200; authenticated /wp-admin/ -> 200
- [x] `npm run env:cli -- core version` returns the installed version
      -> 7.1-beta2-62791-src
- [x] A representative PHP test executes through the official runner
      -> `npm run test:php -- --filter test_the_basics` => "OK (4 tests, 37 assertions)"
- [x] Test users created for each privilege level
      -> admin + subscriber + contributor + author + editor (see Test accounts)

## Test accounts (LOCAL-ONLY, non-personal lab credentials — rotate/dispose as needed)
| Role         | User login   | Capability class      | Password (lab-only) |
|--------------|--------------|-----------------------|----------------------|
| Anonymous    | (none)      | no auth               | n/a                  |
| Subscriber   | subscriber   | read                  | SubPass_9q2x         |
| Contributor  | contributor  | edit_posts (own)     | ConPass_4mLk         |
| Author       | author       | edit/publish own     | AuthPass_7kRm        |
| Editor       | editor       | edit/publish others  | EdPass_2wXp          |
| Administrator| admin        | manage_options (all) | password             |
- Created via `npm run env:cli -- user create <login> <email> --role=<role> --user_pass=<pw>`
- Emails use @lab.local (non-routable). Passwords are unique and never reused personal creds.

## Evidence captured at setup
- Baseline DB snapshot (before research): evidence/db-snapshots/baseline-d792cbd.sql
  (created via `npm run env:cli -- db export -`, cleaned of CLI preamble; 681 lines)
- Directory structure:
  - evidence/attack-surface-inventory.md  (Phase A skeleton, populated with entry-point map)
  - evidence/candidate-register.md        (scaffold; empty — research not started)
  - evidence/requests/                    (HTTP request/response pairs, no real-user secrets)
  - evidence/db-snapshots/               (before/after DB state)
  - evidence/regression-tests/           (focused phpunit tests for confirmed behavior)
  - evidence/logs/                       (container logs: WP/PHP/web/MySQL)
- Capture helpers (run from lab root):
  - Request/response: `curl -v http://localhost:8889/...` (or proxy); store in evidence/requests/
  - DB before/after: `npm run env:cli -- db export - 2>/dev/null > evidence/db-snapshots/<label>.sql`
  - Container logs: `docker logs wordpress-develop-wordpress-develop-1`, `...-php-1`, `...-mysql-1`
  - Reset (DESTRUCTIVE, only after preserving evidence): `npm run env:reset`

## Notes
- Engine check: package.json requires node>=20.10.0 / npm>=10.2.3; host has 26.5.0 / 11.17.0.
  The >= floor is satisfied, so setup succeeded without `--engine-strict`. The 20.x/10.x targets
  in the PRD are recommendations (see .nvmrc); the deviation is recorded, not silently ignored.
- Local-env (NOT public wp-env) is used: `env:start` builds the official develop image and brings
  containers up in detached mode; `env:install` generated wp-config.php and installed WordPress.
- Keep candidate details, exploit code, and evidence OUTSIDE public Git history. The .security-research
  tree is intentionally separate from the NetPath application repo.
- A finding or bounty is not guaranteed. Do not test any system other than this local lab.
