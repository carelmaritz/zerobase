# TASK-M004: Trusted-proxy support for client addresses

**Status**: TODO
**Priority**: M - Medium
**Effort**: S - 1-2 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-M004
**Dependencies**: None

---

## Objective

When the app runs behind Caddy (the recommended setup) or another reverse proxy, use the real client address from the proxy's forwarding headers so login throttling is per client, without letting direct clients spoof that header.

---

## Background

The login throttle keys on `request.client.host + email` (`routers/auth.py`). uvicorn only honours `X-Forwarded-For` from addresses in `--forwarded-allow-ips` (default `127.0.0.1`). In the Compose setup Caddy reaches the app over the Docker network from a different address, so every request appears to come from Caddy's container IP.

Effect: throttling becomes per-email only. Someone who knows a user's email can lock that user out for 15 minutes from anywhere by failing 8 sign-ins. The README already flags this as a known limitation.

---

## Technical Requirements

- A setting (e.g. `ZEROBASE_TRUSTED_PROXIES`, comma-separated IPs/CIDRs, default empty) passed to uvicorn's proxy-header handling (`FORWARDED_ALLOW_IPS` / `--forwarded-allow-ips`) or to Starlette/uvicorn `ProxyHeadersMiddleware` in the app factory.
- Compose proxy profile sets it to Caddy's address on a fixed Docker network subnet (or Caddy's service network), not `*`.
- Never trust forwarding headers by default: with `*`, anyone hitting port 8000 directly could forge `X-Forwarded-For` and bypass the throttle.
- Also respect `X-Forwarded-Proto` so `request.url.scheme` is `https` behind the proxy.
- Check the same-origin check in `main.py` still works (it compares `Origin` to the `Host` header; Caddy forwards Host unchanged by default).

### Success Criteria
- [ ] Behind Caddy, the throttle sees distinct client IPs
- [ ] Direct requests with a forged `X-Forwarded-For` from an untrusted address are not believed
- [ ] Documented in README configuration table and Security notes (remove the "safety net" caveat if fully resolved)

### Out of Scope

- Persisting throttle state across restarts or multiple instances.
- Rate limiting other endpoints.
- Per-account lockout notifications.

---

## Freedom

**Free to decide**: Whether to configure uvicorn via env or add middleware in the app factory.

**Ask first**: Changing the throttle's limits or key, changing the Compose network layout beyond adding a fixed subnet.

---

## Implementation Plan

### Phase 1
- [ ] Add setting and wire it up
- [ ] Compose and Caddyfile changes
- [ ] Tests: unit test with a fake trusted proxy and a forged header from an untrusted one
- [ ] README

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Trusted proxy + `X-Forwarded-For: 203.0.113.5`: throttle key uses 203.0.113.5
- [ ] Untrusted source + same header: header ignored
- [ ] Manual: `docker compose --profile proxy up`, fail logins from two machines, only one is throttled

---

## Security Considerations

- Trusting `*` is the main way to get this wrong. Default must be no trusted proxies.

---

## Related Tasks

- **Depends On**: None
- **Blocks**: None
- **Related**: None

---

## References

- uvicorn proxy settings: https://www.uvicorn.org/settings/#http

---

*Last Updated: 2026-10-21 by Claude*
