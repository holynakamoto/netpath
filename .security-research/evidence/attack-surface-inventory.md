# Attack-Surface Inventory — WordPress Core (trunk)

Lab: `/Users/nickmoore/netpath/.security-research/wordpress-develop`
Source revision: `d792cbd66941a708d62b1778f044393206b95c63` (trunk)
Disclosure route: https://hackerone.com/wordpress
Scope: WordPress Core only. Plugins excluded unless listed in-scope by the program.
Status legend: ☐ not analyzed · 🔶 in progress · ✅ analyzed · 🚩 candidate

This inventory enumerates attacker-controlled entry points and their privilege/permission
callbacks per PRD § Phase A. For each, record the registration mechanism, the default
permission callback, and the boundary it enforces. A finding only matters if an
unauthenticated or lower-privileged caller can reach a sensitive sink the callback was
supposed to block (PRD § Phase B).

---

## A1. REST API routes (incl. batch + nested dispatch)
Source: `wp-includes/rest-api/class-wp-rest-server.php`, `wp-includes/rest-api.php`,
`wp-includes/rest-api/*`, `wp-includes/blocks.php` (block patterns/templates).
- Registration: `register_rest_route( $namespace, $route, [ 'permission_callback' => ... ] )`.
- Batch endpoint: `POST /wp-json/wp/v2/batch` → `WP_REST_Server::serve_batch_request()`.
  Each sub-request carries its own `permission_callback`; verify batch does not bypass it.
- Nested/plural dispatch: `WP_REST_Posts_Controller` `get_items`/`get_item` permission
  checks; verify `id` vs `id>...` vs array handling, and `context=edit` requires edit caps.
- Key controllers to triage: posts, pages, media, users (🔴 high value), comments,
  plugins/themes (only when `DISALLOW_FILE_MODS` off + caps), block-directory, patterns,
  global-styles, navigation, templates/template-parts, themes (WP 6.x site editor).
- Verify: unauth can list what? `users` endpoint must be `is_user_logged_in()` gated
  (core hardening since 4.7). Re-check `search`/enumeration leaks.

## A2. AJAX actions (auth + unauth)
Source: `wp-admin/admin-ajax.php`, `wp-includes/plugin.php` (`wp_ajax_*`, `wp_ajax_nopriv_*`).
- Unauth hooks fire only for `wp_ajax_nopriv_<action>`; verify each nopriv action performs
  its own capability/auth check (many rely solely on the action name, not a callback).
- High-value nopriv actions: `nopriv_heartbeat`, `nopriv_generate_password` (no),
  `nopriv_autosave` (no), `nopriv_send_attachment_to_editor`, `nopriv_ipt_dismiss`,
  `nopriv_oembed`? Check `wp_ajax_nopriv_*` registrations in core + blocks.
- Verify CSRF: most auth ajax require nonce; nopriv actions often skip nonce — confirm no
  state-changing nopriv action lacks authorization.

## A3. XML-RPC methods (only where concrete impact exists)
Source: `xmlrpc.php`, `wp-includes/class-wp-xmlrpc-server.php`.
- Methods: `wp.getUsersBlogs`, `wp.getUser`, `metaWeblog.getPost`, `mw_newPost`,
  `wp.newComment`, `pingback.ping` (🔴 pingback SSRF/history historically),
  `system.multicall` (batch — verify per-method auth, not just outer auth).
- Verify: `wp.uploadFile` auth, `demo.*` disabled by default, `pingback.ping` data flow.

## A4. Upload / media / archive / image / filesystem processing
Source: `wp-admin/includes/file.php` (`wp_handle_upload`, `wp_check_filetype_and_ext`),
`wp-admin/includes/image.php`, `wp-admin/includes/media.php`,
`wp-includes/class-wp-image-editor*.php`, `wp-admin/includes/class-pclzip.php`,
ZipArchive usage, `wp-includes/ID3/*` (metadata parsing).
- Verify: filetype allow-list enforcement, `.phtml`/`.pht`/`.html` on allowed types,
  image editor command injection (ImageMagick/GD), EXIF/ID3 parser memory/object issues,
  ZIP extraction path traversal (`../`), theme/plugin upload (caps gated).

## A5. Authentication / password reset / app passwords / sessions
Source: `wp-includes/pluggable.php`, `wp-login.php`, `wp-includes/user.php`,
`wp-includes/class-wp-session-tokens.php`, `wp-includes/class-wp-user.php`,
`wp-includes/class-wp-application-passwords.php`, `wp-includes/rest-api/`
(`/wp/v2/users/me` application-password auth).
- Verify: password-reset token generation/consumption (`get_password_reset_key`,
  `check_password_reset_key`), `wp-login.php` `action=rp`/`action=resetpass`,
  application-password capabilities + IP/user-agent binding, session token invalidation on
  logout/role change, `remember_me` cookie duration, brute-force / rate-limit absence
  (note: not a vuln by itself; only if it crosses a boundary).

## A6. Post meta / options / object cache / cron / background
Source: `wp-includes/meta.php`, `wp-includes/option.php`, `wp-includes/cache.php`,
`wp-includes/cron.php`, `wp-includes/class-wp-meta-query.php`.
- Verify: `update_post_meta`/`add_post_meta` capability checks on `meta_key` (e.g.
  protected `_` prefix enforcement), `update_option` on protected options
  (`_transient_`, `active_plugins`, `siteurl`, `home`, `admin_email`, `new_admin_email`),
  `alloptions` cache poisoning, cron `wp_schedule_event` with attacker-controlled hook
  (dynamic callback), object cache (external cache auth/deserialization if configured).

## A7. Serialization / deserialization / dynamic callbacks
Source: `wp-includes/functions.php` (`maybe_unserialize`, `is_serialized`),
`wp-includes/plugin.php` (`add_filter`/`add_action` with dynamic `$callback`),
`wp-includes/class-wp-hook.php`.
- Verify: any `unserialize()`/`maybe_unserialize()` over attacker-influenced data that can
  populate a POP chain (note: core has few `__destruct`/`__wakeup` gadgets; focus on
  cache/transient with object cache backends). Dynamic callback invocation where the
  callable is derived from request input (e.g. `call_user_func` on user data).

## A8. SQL construction — scalar vs array handling
Source: `wp-includes/class-wpdb.php` (`prepare`, `esc_sql`, `get_results`, `query`),
`wp-includes/class-wp-meta-query.php`, `wp-includes/class-wp-tax-query.php`,
`wp-includes/class-wp-date-query.php`, `wp-includes/class-wp-comment-query.php`.
- 🔴 High-value: `wpdb::prepare()` with mismatched `%s`/`%d` placeholders, second-order
  where an array is passed where a scalar string is concatenated, `IN (...)` clause built
  from unsanitized arrays, `orderby`/`order` allow-list bypass, `LIKE` escaping,
  `wpdb::prepare` returning `null`/`false` on placeholder mismatch (caller may skip check).
- Verify WP_Query `meta_query`/`tax_query` array-depth handling and `fields`/`orderby`.

## A9. Multisite-specific privilege boundaries
Source: `wp-includes/ms-functions.php`, `wp-includes/ms-default-filters.php`,
`wp-includes/ms-load.php`, `wp-admin/network/*`, `switch_to_blog()`.
- Verify: cross-site capability escalation (a subscriber on site A affecting site B),
  `grant_super_admin`, `revoke_super_admin`, `add_user_to_blog` auth,
  `upload_filetypes`/site option edits, `wpmu_new_blog` injection, domain/path validation.

---

## Privilege-boundary cross-check matrix (to fill during triage)
| Entry point | Default required cap | Can unauth reach? | Can sub/contrib reach? | Notes |
|---|---|---|---|---|
| REST /wp/v2/users | `list_users` (logged-in) | ❌ (hardened) | partial (self) | confirm no leak |
| REST media upload | `upload_files` | ❌ | author+ | |
| AJAX nopriv_* | none (own check) | ✅ by design | — | verify each |
| xmlrpc pingback | none | ✅ | — | SSRF history |
| reset password | unauth (token) | ✅ | — | token brute? |

## Rejected / cleared areas (log as covered)
_To be filled during Phase B triage. Each "safe" area gets a one-line rationale so the
coverage is auditable._
