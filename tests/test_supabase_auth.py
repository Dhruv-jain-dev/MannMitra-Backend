from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.core.auth import AuthService


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return self.body


class SupabaseAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.private_key.public_key()))
        public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
        cls.jwks = json.dumps({"keys": [public_jwk]}).encode()
        cls.subject = str(uuid4())
        cls.issuer = "https://example.supabase.co/auth/v1"

    def service(self) -> AuthService:
        return AuthService(None, self.issuer, jwks_url="https://example.test/jwks", audience="authenticated", allow_legacy_tokens=False)

    def token(self, **overrides) -> str:
        claims = {"sub": self.subject, "iss": self.issuer, "aud": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 300}
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "test-key"})

    def test_valid_jwt_uses_jwks_and_uuid_subject(self) -> None:
        with patch("backend.core.auth.urlopen", return_value=_Response(self.jwks)):
            self.assertEqual(self.service().verify_access_token(self.token()).id, self.subject)

    def test_invalid_signature_is_rejected(self) -> None:
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode({"sub": self.subject, "iss": self.issuer, "aud": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 300}, other, algorithm="RS256", headers={"kid": "test-key"})
        with patch("backend.core.auth.urlopen", return_value=_Response(self.jwks)), self.assertRaises(Exception):
            self.service().verify_access_token(token)

    def test_claim_and_algorithm_validation(self) -> None:
        with patch("backend.core.auth.urlopen", return_value=_Response(self.jwks)):
            for claims in ({"iss": "wrong"}, {"aud": "wrong"}, {"exp": int(time.time()) - 1}, {"sub": "not-a-uuid"}):
                with self.assertRaises(Exception):
                    self.service().verify_access_token(self.token(**claims))
        token = jwt.encode({"sub": self.subject, "iss": self.issuer, "aud": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 300}, "not-used", algorithm="HS256")
        with patch("backend.core.auth.urlopen", return_value=_Response(self.jwks)), self.assertRaises(Exception):
            self.service().verify_access_token(token)


if __name__ == "__main__":
    unittest.main()
