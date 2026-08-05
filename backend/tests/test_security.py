"""Unit tests for password hashing and token primitives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_the_plaintext(self) -> None:
        hashed = hash_password("Subnetting2024")
        assert hashed != "Subnetting2024"
        assert hashed.startswith("$argon2")

    def test_verify_accepts_correct_password(self) -> None:
        assert verify_password("Subnetting2024", hash_password("Subnetting2024"))

    def test_verify_rejects_wrong_password(self) -> None:
        assert not verify_password("wrong-password", hash_password("Subnetting2024"))

    def test_verify_rejects_malformed_hash(self) -> None:
        """A corrupted hash must return False, never raise."""
        assert not verify_password("anything", "not-a-real-hash")

    def test_salting_makes_hashes_unique(self) -> None:
        assert hash_password("same-password") != hash_password("same-password")


class TestAccessTokens:
    def test_round_trip_preserves_claims(self) -> None:
        token, expires_at = create_access_token("user-123", "student")
        payload = decode_access_token(token)

        assert payload.subject == "user-123"
        assert payload.role == "student"
        assert payload.expires_at == expires_at.replace(microsecond=0)

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_access_token("user-123", "student", timedelta(seconds=-10))
        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_tampered_token_is_rejected(self) -> None:
        token, _ = create_access_token("user-123", "student")
        header, payload, signature = token.split(".")
        forged = f"{header}.{payload}.{signature[:-4]}AAAA"
        with pytest.raises(TokenError):
            decode_access_token(forged)

    def test_token_signed_with_another_key_is_rejected(self) -> None:
        import jwt

        forged = jwt.encode(
            {
                "sub": "attacker",
                "type": "access",
                "iss": "network-learning-platform",
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            "an-attacker-controlled-key",
            algorithm="HS256",
        )
        with pytest.raises(TokenError):
            decode_access_token(forged)

    def test_each_token_has_a_unique_id(self) -> None:
        first, _ = create_access_token("user-123", "student")
        second, _ = create_access_token("user-123", "student")
        assert decode_access_token(first).token_id != decode_access_token(second).token_id


class TestRefreshTokens:
    def test_generated_tokens_are_unique_and_long(self) -> None:
        tokens = {generate_refresh_token() for _ in range(100)}
        assert len(tokens) == 100
        assert all(len(token) >= 43 for token in tokens)

    def test_hash_is_deterministic(self) -> None:
        token = generate_refresh_token()
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_hash_does_not_reveal_the_token(self) -> None:
        token = generate_refresh_token()
        digest = hash_refresh_token(token)
        assert token not in digest
        assert len(digest) == 64  # SHA-256 hex
