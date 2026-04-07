# Auth Component

## Purpose
Handles all authentication concerns: user registration, login, JWT access/refresh token issuance, token refresh, and logout (refresh token revocation). This is the security foundation that all other components depend on.

## Scope

### In Scope
- User registration (email + password)
- Login with credential verification
- JWT access token generation (short-lived, 15 min)
- JWT refresh token issuance and storage (7 days)
- Token refresh endpoint (exchange refresh token for new access token)
- Logout (revoke refresh token)
- `get_current_user` dependency used across all protected routes

### Out of Scope
- User profile updates (owned by `users` component)
- Role-based access control enforcement (enforced per-component at service layer)
- OAuth / social login
- Password reset / email verification

## Responsibilities
- Validate email uniqueness on registration
- Hash passwords with bcrypt before storage
- Issue signed JWT access tokens with `sub` (user ID) and `exp` claims
- Issue refresh tokens: store hashed token in `refresh_tokens` table with expiry
- Verify refresh token on exchange: check hash match, not expired, not revoked
- Mark refresh token as revoked on logout
- Provide `get_current_user` FastAPI dependency that decodes JWT and loads user

## Dependencies
- `users` models (User table, create user)
- `core/security.py` (JWT sign/verify, password hash/verify)
- `core/database.py` (async DB session)

## Related Models
- `User` (read/create)
- `RefreshToken` (create/read/update)

## Related Endpoints
- `POST /api/v1/auth/register` — create user account
- `POST /api/v1/auth/login` — authenticate, return access + refresh tokens
- `POST /api/v1/auth/refresh` — exchange refresh token for new access token
- `POST /api/v1/auth/logout` — revoke refresh token

## Business Rules
- Email must be unique (case-insensitive)
- Password minimum length: 8 characters
- Access token TTL: 15 minutes
- Refresh token TTL: 7 days
- Refresh tokens are single-use: each refresh issues a new refresh token and revokes the old one (rotation)
- Revoked or expired refresh tokens must be rejected
- Multiple refresh tokens per user are allowed (multiple devices)

## Security Considerations
- Passwords hashed with bcrypt, cost factor 12 minimum
- Refresh tokens hashed with SHA-256 before storage — raw token never stored
- JWT signed with HS256 using `JWT_SECRET_KEY` from env
- Login endpoint rate-limited: 5 attempts/minute per IP
- No user enumeration: registration and login errors should not reveal whether email exists
- Tokens not logged

## Performance Considerations
- bcrypt is intentionally slow — acceptable cost for login
- Refresh token lookup by hash: index on `refresh_tokens.token_hash`
- JWT verification is in-memory — no DB call needed for protected route auth

## Reliability Considerations
- Refresh token revocation is idempotent — revoking an already-revoked token is a no-op
- If refresh token DB write fails, the old token remains valid (acceptable — retry is safe)

## Testing Expectations
- Unit: password hashing, JWT generation/verification
- Integration: full register → login → refresh → logout flow
- Permission: expired/revoked/invalid tokens return 401
- Rate limit: 6th login attempt within 1 minute returns 429
- Security: verify raw refresh token not stored in DB

## Implementation Notes
- `core/security.py`: `create_access_token()`, `decode_access_token()`, `hash_password()`, `verify_password()`, `hash_refresh_token()`
- `auth/service.py`: `register_user()`, `authenticate_user()`, `refresh_access_token()`, `logout_user()`
- `auth/router.py`: thin, calls service, returns `ApiResponse`
- `core/dependencies.py`: `get_current_user` dependency decodes JWT, fetches User, raises 401 if invalid

## Status
complete

## Pending Tasks
- None

## Completion Notes
- `app/core/security.py`: `hash_password`, `verify_password`, `create_access_token`, `decode_access_token`, `generate_refresh_token`, `hash_refresh_token`
- `app/auth/models.py`: `RefreshToken` with `token_hash` (SHA-256 hex, never raw), `expires_at`, `revoked`
- `app/auth/service.py`: full register/authenticate/refresh/logout logic with token rotation; timing-safe login using dummy hash when user not found
- `app/auth/router.py`: thin; login rate-limited 5/min per IP via `slowapi`
- `app/core/dependencies.py`: `get_current_user` decodes JWT, validates UUID, loads User; raises 401 on any failure
- `app/core/exceptions.py`: named `ForbiddenError` (not `PermissionError`) and `AppValidationError` (not `ValidationError`) to avoid shadowing Python builtins
- Tests: 12 service tests + 13 router tests covering happy paths, failure paths, rotation, idempotency, multi-device, response shape
