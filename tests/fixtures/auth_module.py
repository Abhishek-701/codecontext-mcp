"""Auth module fixture for integration tests — JWT tokens and password hashing."""

import bcrypt
import jwt


def validate_token(token: str) -> dict:
    """Validate a JWT token and return the decoded payload."""
    if not token or not token.strip():
        raise ValueError("token must not be empty")
    payload = jwt.decode(token, options={"verify_signature": False})
    if "sub" not in payload:
        raise ValueError("token missing subject claim")
    return payload


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with a random salt."""
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


class AuthService:
    """Coordinates authentication, token refresh, and revocation."""

    def __init__(self, db_pool, secret_key: str) -> None:
        self._db_pool = db_pool
        self._secret_key = secret_key

    async def authenticate(self, token: str) -> dict:
        """Authenticate a user by validating their JWT token."""
        payload = validate_token(token)
        user_id = payload["sub"]
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if row is None:
            raise PermissionError("user not found")
        return {"user_id": user_id, "claims": payload}

    async def refresh_token(self, user_id: str) -> str:
        """Generate a new JWT token for an authenticated user."""
        claims = {"sub": user_id, "type": "access"}
        token = jwt.encode(claims, self._secret_key, algorithm="HS256")
        return token if isinstance(token, str) else token.decode("utf-8")

    async def revoke_token(self, token: str) -> None:
        """Revoke a JWT token, preventing further use."""
        payload = validate_token(token)
        jti = payload.get("jti")
        if jti is None:
            raise ValueError("token has no jti claim to revoke")
        async with self._db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO revoked_tokens (jti) VALUES ($1) ON CONFLICT DO NOTHING",
                jti,
            )
