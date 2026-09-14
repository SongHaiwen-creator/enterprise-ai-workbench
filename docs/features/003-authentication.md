# Feature 003 - Authentication Foundation

Status: Draft
Milestone: 1

## 1. Goal

Introduce user authentication so that backend requests can identify
the current platform user.

This feature answers:

"Who is making this request?"

It does not yet answer:

"Is this user allowed to perform this action?"

Authorization and RBAC will be implemented separately.

---

## 2. Authentication Method

The MVP uses:

- Email + password login
- Password hashing with Argon2id
- JWT access tokens
- Bearer token authentication

Refresh tokens are not included in this milestone.

Enterprise SSO is also out of scope.

---

## 3. User Credential Storage

The User model will store:

- password_hash

Plain-text passwords must never be persisted.

Password flow:

Password
→ Argon2id hash
→ password_hash stored in PostgreSQL

During login:

Submitted password
→ Verify against password_hash
→ Authentication succeeds or fails

---

## 4. Login API

Endpoint:

POST /api/auth/login

Request:

```json
{
  "email": "alice@company.com",
  "password": "example-password"
}

Success:

HTTP 200 OK

Response:

{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 1800
}

Rules:

Email is normalized using the existing lowercase behavior.
Incorrect email or password returns HTTP 401.
Error responses must not reveal whether the email exists.
Disabled users cannot log in.
5. Current User

Protected endpoints can resolve the authenticated User from:

Authorization: Bearer <access_token>

Flow:

Request
→ Extract Bearer Token
→ Validate JWT
→ Read user ID from token
→ Load User from PostgreSQL
→ Return Current User

6. Current User API

Endpoint:

GET /api/auth/me

Success:

HTTP 200 OK

Response:

{
  "id": "user-uuid",
  "email": "alice@company.com",
  "name": "Alice",
  "status": "active"
}

Errors:

Missing token → 401
Invalid token → 401
Expired token → 401
User no longer exists → 401
Disabled user → 403
7. Token Policy

Access token lifetime:

30 minutes.

JWT should contain only minimal identity information.

Required claim:

sub: User ID

Standard claims should include:

exp
iat

Sensitive information must not be stored in the JWT.

8. User Provisioning

Public user registration is not supported.

Development and test users will be created through:

test fixtures
development seed or controlled setup process

A public POST /register endpoint must not be introduced.

9. Security Rules
Plain-text passwords must never be stored.
Passwords must not appear in logs.
JWT signing secret must come from environment configuration.
JWT signing secret must never be committed to Git.
Invalid login responses must not reveal whether an email exists.
Disabled users must not authenticate successfully.
Authentication does not replace RBAC authorization.
10. Out of Scope

This feature does NOT implement:

User registration
Refresh tokens
Logout token revocation
Password reset
MFA
Enterprise SSO
OAuth login
Workspace RBAC
Permission middleware
Knowledge Base
RAG
Agent
AI functionality

## 11. Database Migration Requirements

The existing User table must be extended with:

- password_hash

A new Alembic migration must be created.

The existing initial migration must NOT be rewritten.

Migration sequence:

0001
Create users / workspaces / memberships

↓

0002
Add password_hash to users

Requirements:

- password_hash must not store plain-text passwords.
- The migration must be reversible.
- Existing schema and data must remain valid.
- Authentication-related schema changes must be introduced only
  through the new migration.

---

## 12. Authentication Flow

### Login

Client
↓
POST /api/auth/login
↓
Normalize email
↓
Load User
↓
Verify password hash
↓
Check User status
↓
Create JWT access token
↓
Return token

---

### Authenticated Request

Client
↓
Authorization: Bearer <token>
↓
Validate JWT signature
↓
Validate expiration
↓
Read sub claim
↓
Load current User
↓
Check User status
↓
Provide Current User to endpoint

---

## 13. Acceptance Criteria

### AC-001 - Successful Login

Given:

An active User exists with a valid password hash.

When:

The correct email and password are submitted to:

POST /api/auth/login

Then:

- HTTP 200 is returned.
- An access token is returned.
- token_type is `bearer`.
- expires_in is returned.
- The access token contains the User ID in the `sub` claim.

---

### AC-002 - Email Normalization

Given:

The stored User email is:

alice@company.com

When:

The login request uses:

Alice@Company.com

Then:

Authentication succeeds when the password is correct.

---

### AC-003 - Incorrect Password

Given:

A valid User exists.

When:

An incorrect password is submitted.

Then:

HTTP 401 is returned.

The response must not reveal that the email exists.

---

### AC-004 - Unknown Email

Given:

No User exists for the submitted email.

When:

Login is attempted.

Then:

HTTP 401 is returned.

The error response should be indistinguishable from an incorrect
password response.

---

### AC-005 - Disabled User Login

Given:

A User has status `disabled`.

When:

The correct email and password are submitted.

Then:

HTTP 403 is returned.

No access token is issued.

---

### AC-006 - Current User

Given:

An active User has a valid access token.

When:

GET /api/auth/me is called with:

Authorization: Bearer <token>

Then:

HTTP 200 is returned with:

- id
- email
- name
- status

Password hash must never appear in the response.

---

### AC-007 - Missing Token

When:

GET /api/auth/me is called without an Authorization header.

Then:

HTTP 401 is returned.

---

### AC-008 - Invalid Token

When:

GET /api/auth/me is called with an invalid JWT.

Then:

HTTP 401 is returned.

---

### AC-009 - Expired Token

Given:

An access token is expired.

When:

It is used to call an authenticated endpoint.

Then:

HTTP 401 is returned.

---

### AC-010 - Deleted User

Given:

A token was previously issued for a User.

When:

The User no longer exists in PostgreSQL.

Then:

The token must not be sufficient by itself.

HTTP 401 is returned.

---

### AC-011 - Disabled User After Token Issuance

Given:

A valid token exists for a User.

When:

The User is later disabled.

Then:

GET /api/auth/me returns HTTP 403.

---

### AC-012 - Password Storage

When:

A development/test User is created with a password.

Then:

- The plain-text password is not persisted.
- password_hash is persisted.
- The original password can be verified against the hash.
- An incorrect password fails verification.

---

### AC-013 - Existing APIs

Authentication implementation must not break:

- GET /health
- Workspace APIs
- Membership APIs
- Existing PostgreSQL migrations
- Existing database integration tests

The Workspace and Membership APIs remain temporarily unauthenticated
until the RBAC feature is implemented.

---

## 14. Testing Requirements

Tests must cover authentication behavior without using a fake password
implementation.

### Password Tests

Test:

- Password hashing succeeds.
- Hash differs from the original password.
- Correct password verifies.
- Incorrect password fails.
- Same password produces valid salted hashes rather than relying on
  deterministic plaintext comparison.

---

### Login API Tests

Test:

- Successful login.
- Case-insensitive email login.
- Wrong password.
- Unknown email.
- Disabled User.
- Unknown request fields.
- Invalid request body.

---

### JWT Tests

Test:

- Token contains expected `sub`.
- Token includes expiration.
- Valid token resolves Current User.
- Invalid signature returns 401.
- Malformed token returns 401.
- Expired token returns 401.

---

### Current User Tests

Test:

- GET /api/auth/me with valid token.
- Missing token.
- Unknown User referenced by token.
- Disabled User referenced by token.
- Response never contains password_hash.

---

### Migration Tests

Test:

- Migration 0002 upgrades from the existing 0001 schema.
- password_hash exists after upgrade.
- Migration reaches Alembic head.
- Downgrade behavior is valid if downgrade is supported by the project
  migration policy.

PostgreSQL must remain the persistence test database.

SQLite must not be introduced.

---

## 15. Environment Configuration

Authentication requires a JWT signing secret.

Add a safe placeholder to `.env.example`:

JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

The real JWT secret must exist only in `.env`.

It must not be committed to Git.

Production-grade secret rotation is out of scope for this milestone.

---

## 16. API Endpoints

This feature introduces:

POST /api/auth/login

GET /api/auth/me

No public registration endpoint is added.

---

## 17. Completion Definition

This feature is complete when:

- User password hashes are persisted through migration 0002.
- Password verification uses Argon2id.
- Login returns a valid JWT access token.
- Authenticated requests can resolve the Current User.
- Disabled users are blocked.
- Invalid and expired tokens are rejected.
- Authentication tests pass against PostgreSQL.
- Existing Workspace/Membership APIs continue to pass.
- Ruff passes.
- Frontend lint/build continue to pass.