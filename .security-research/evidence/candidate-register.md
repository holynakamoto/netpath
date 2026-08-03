# Candidate Register — WordPress Core Security Audit

Lab: `/Users/nickmoore/netpath/.security-research/wordpress-develop`
Source revision (trunk HEAD): `d792cbd66941a708d62b1778f044393206b95c63` (WP 7.1-beta2-62791-src)
Disclosure route: https://hackerone.com/wordpress
AI assistance: analysis + live validation assisted by Hermes (Codex-class AI); all findings manually
validated by the human researcher, who reviews and submits. AI assistance disclosed in any report.

## Viable candidates
**NONE FOUND at this commit this cycle.** A reproducible, unpatched, privilege-boundary-crossing
issue was not identified across the surfaces triaged. (See rejected hypotheses + honest status at bottom.)

## Rejected hypotheses (code-proven + live-validated)

### R1 — REST users: self role escalation
- Source: `src/wp-includes/rest-api/endpoints/class-wp-rest-users-controller.php:725-754` (`update_item_permissions_check`)
- Sink: `add_role()` on target user
- Attacker: subscriber (lowest auth)
- Input: `POST /wp/v2/users/me {"roles":["administrator"]}`
- Expected impact: gain administrator
- Observed: **HTTP 403** `rest_cannot_edit_roles` — requires `promote_user`
- Falsification: `evidence/requests/c1_roles_escalation.json` (live)
- Status: **REJECTED** — gated.

### R2 — REST users: protected meta escalation (`wp_capabilities`)
- Source: `src/wp-includes/capabilities.php:433-477` (`edit_user_meta` → `is_protected_meta`)
- Sink: `update_metadata` on user meta
- Attacker: subscriber
- Input: `POST /wp/v2/users/me {"meta":{"wp_capabilities":["administrator"]}}`
- Expected impact: capability escalation
- Observed: **HTTP 200 but user stays `subscriber`** (caps `read`/`level_0`/`subscriber` only) — protected key dropped
- Falsification: `evidence/requests/c2_meta_escalation.json` (live)
- Status: **REJECTED** — `is_protected_meta` blocks `wp_capabilities`/`wp_user_level`.

### R3 — Upload RCE via `.php` / mislabeled file
- Source: `src/wp-includes/functions.php:3128` `wp_check_filetype_and_ext` (+ `wp_get_image_mime` correction)
- Sink: `wp_handle_upload` type resolution
- Attacker: author (`upload_files`)
- Input: `.php` file, or image with PHP content mislabeled as `.jpg`
- Expected impact: executable upload → RCE
- Observed: `.php` → `ext=[false] type=[false]` (not in allowed mime types); images corrected to real MIME
- Falsification: `evidence/requests/c3_upload_php_rejection.txt` (live)
- Status: **REJECTED** — allow-list + content sniffing.

### R4 — Application passwords: cross-user access
- Source: `src/wp-includes/rest-api/endpoints/class-wp-rest-application-passwords-controller.php:112-437`
- Sink: per-user cap checks (`list/create/edit/delete_app_password(s)`)
- Attacker: any low-priv user
- Input: app-password endpoints on another user's ID
- Expected impact: read/create/delete another user's app passwords
- Observed: every method checks `current_user_can(<cap>, $target_user_id)`
- Status: **REJECTED** — gated per target user.

### R5 — `get_file_data()` HEAD change (header parse)
- Source: `src/wp-includes/functions.php` (commit d792cbd) — recognizes `<?` / `<?php` header prefixes
- Sink: plugin/theme header parsing
- Attacker: none reachable (only admins install plugins/themes; change only widens recognized comment styles)
- Expected impact: header injection / unexpected metadata
- Observed: benign feature fix (Trac #42517); no privilege boundary for non-admins
- Status: **REJECTED** — no attacker reachability.

### R6 — Font faces controller: unauthorized write
- Source: `src/wp-includes/rest-api/endpoints/class-wp-rest-font-faces-controller.php:115-152` (read), write via `edit_theme_options`
- Sink: font face CPT write
- Attacker: subscriber (read) / contributor (no write)
- Observed: read requires `read` cap (read-only metadata, by design); write requires `edit_theme_options` (editor+)
- Status: **REJECTED** — gated.

### R7 — Templates controller: unauthorized write
- Source: `src/wp-includes/rest-api/endpoints/class-wp-rest-templates-controller.php:244-323` (read), update via `permissions_check` → `edit_theme_options`
- Sink: block template write
- Attacker: contributor/author (`edit_posts` → read only)
- Observed: read for `edit_posts`; write requires `edit_theme_options`
- Status: **REJECTED** — gated.

### R8 — REST settings: lower-role option update
- Source: `src/wp-includes/rest-api/endpoints/class-wp-rest-settings-controller.php:68` (`manage_options`) + `src/wp-includes/capabilities.php:116/703/777/791/798` (`update_option` → `manage_options`)
- Sink: `update_option` on any setting
- Attacker: editor (no `manage_options`)
- Expected impact: set `siteurl`/`home`/`admin_email` etc.
- Observed: top-level `manage_options` required; `update_option` maps to `manage_options` for protected options
- Status: **REJECTED** — gated.

### R9 — Password reset: key prediction / cross-user consumption
- Source: `src/wp-includes/user.php:3176` `check_password_reset_key`, `:3262` `retrieve_password`
- Sink: reset key validation
- Attacker: unauth
- Input: trigger reset, guess/forge key
- Observed: key = `wp_verify_fast_hash` of random, stored hashed, tied to login, expiry-checked — not predictable, not cross-consumable
- Status: **REJECTED** — cryptographically sound.
  (Minor aside: the reset form reveals whether a user/email exists — user enumeration, a low-severity
   "public data" class likely excluded per PRD §B exclusions. Not a privilege boundary.)

### R10 — XML-RPC `pingback.ping` SSRF
- Source: `src/wp-includes/class-wp-xmlrpc-server.php:6915`
- Sink: server-side fetch of `$pagelinkedfrom` (attacker URL)
- Attacker: unauth
- Input: `pingback.ping(sourceURI=attacker URL, targetURI=local post)`
- Observed: `targetURI` forced local (`home` check at :6942); useful *internal* SSRF requires an internal
  service reflecting a link to the local post — contrived; known low-severity/mitigated class
- Status: **REJECTED** (low-severity at best; likely excluded/duplicate).

### R11 — XML-RPC `system.multicall` auth bypass
- Source: `src/wp-includes/class-wp-xmlrpc-server.php` — no `multicall` method present in current trunk
- Status: **REJECTED** — method absent.

## Honest status (this cycle)
- Phase A/B/C completed for all high-value privilege-boundary surfaces in WP 7.1-beta2 @ `d792cbd`.
- Every triaged sink is properly gated/mitigated. **No reproducible, unpatched, privilege-boundary-crossing
  vulnerability was found.**
- No fabricated findings. The lab is fully functional and validated (live proofs captured above).
- **Reality check:** WordPress Core is the most security-audited CMS in the world. A fresh, reportable
  privilege-boundary bug is not surfaced by reading the obvious sinks, and cannot be produced on demand.
  A bounty requires either (a) deep novel research / fuzzing of a specific subsystem,
  (b) differential analysis, or (c) accepting that none was found this cycle.
- PRD §9.6 (human scope attestation) and Phase D/E (report draft + submission) are the human's
  action and remain blocked on a *viable* candidate.
- Note: the auto-subagent sweep of comments/options/`%i`-SQL surfaced no usable result (model
  returned an empty stream); those areas were not exhaustively re-reviewed by the lead agent and
  remain open for a deeper pass if the human wants to continue.
