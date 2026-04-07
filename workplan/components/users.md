# Users Component

## Purpose
Manages user profiles and account state. Provides the `User` model which is the root ownership entity for all knowledge assets in the system.

## Scope

### In Scope
- User model definition
- Read own profile
- Update own profile (name, password change)
- Admin: list all users, deactivate/reactivate user accounts

### Out of Scope
- Authentication (owned by `auth`)
- Knowledge domain management (owned by `domains`)
- Account deletion

## Responsibilities
- Own the `User` SQLAlchemy model
- Expose `GET /users/me` for authenticated user profile
- Expose `PATCH /users/me` for profile updates (full name, password change)
- Admin: `GET /users` list (paginated), `PATCH /users/{id}/deactivate`

## Dependencies
- `auth` component (get_current_user dependency)
- `core/security.py` (password hashing for password change)
- `core/database.py`

## Related Models
- `User`

## Related Endpoints
- `GET /api/v1/users/me` — get own profile
- `PATCH /api/v1/users/me` — update own profile
- `GET /api/v1/admin/users` — list all users (admin only)
- `PATCH /api/v1/admin/users/{user_id}/deactivate` — deactivate user (admin only)

## Business Rules
- Users can only read and update their own profile
- Password change requires current password verification
- Deactivated users cannot authenticate (login returns 403)
- Only admin can deactivate other users
- Email cannot be changed (it is the identity anchor)

## Security Considerations
- `PATCH /users/me` for password change must verify current password before accepting new one
- Admin endpoints require `is_admin` check via dependency
- User ID in path for admin endpoints must not be exploitable — validate against DB

## Performance Considerations
- User profile reads are low-frequency — no caching needed
- Admin user list: paginated, default 20, max 100

## Reliability Considerations
- Profile updates are simple DB writes — no async needed
- Deactivation is reversible (soft disable via `is_active`)

## Testing Expectations
- Unit: password change validation logic
- Integration: update profile, verify DB state
- Permission: user cannot access another user's profile; non-admin cannot access admin endpoints
- Security: deactivated user login returns 403

## Implementation Notes
- `users/models.py`: `User` SQLAlchemy model (already referenced in auth component)
- `users/service.py`: `get_user_by_id()`, `update_user_profile()`, `change_password()`, `deactivate_user()`
- `users/schemas.py`: `UserResponse`, `UserUpdateRequest`, `PasswordChangeRequest`
- Admin operations in separate router: `app/admin/users_router.py`

## Status
complete

## Pending Tasks
- None

## Completion Notes
- `app/users/schemas.py`: `UserResponse` (with `from_attributes=True` — canonical owner), `UpdateProfileRequest` (handles name + password change in one body; password pair validated together via `model_validator`)
- `app/users/service.py`: `get_user_by_id`, `update_user_profile` (uses `model_fields_set` to distinguish omitted vs. explicit null for `full_name`), `list_users` (paginated), `set_user_active`
- `app/users/router.py`: `GET /api/v1/users/me`, `PATCH /api/v1/users/me`
- `app/admin/users_router.py`: `GET /api/v1/admin/users` (paginated), `PATCH /api/v1/admin/users/{id}/deactivate`, `PATCH /api/v1/admin/users/{id}/reactivate`; admin self-deactivation blocked
- `app/core/dependencies.py`: added `require_admin` dependency (403 for non-admin)
- `app/auth/schemas.py`: `UserResponse` removed and re-exported from `users.schemas`; `auth/router.py` updated to use `model_validate`
- `app/auth/service.py`: inactive account login now raises `ForbiddenError` → 403 (was 401, spec requires 403)
- Tests: 13 service tests + 17 router tests (profile CRUD, password change, admin list/deactivate/reactivate, 403 for deactivated login)
