"""密碼雜湊（PBKDF2-SHA256，加鹽）。"""
import hashlib
import hmac
import os

ROUNDS = 240_000


def make(pw: str) -> str:
    salt = os.urandom(16)
    k = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ROUNDS)
    return "pbkdf2_sha256$%d$%s$%s" % (ROUNDS, salt.hex(), k.hex())


def verify(pw: str, stored: str) -> bool:
    try:
        _, rounds, salt, k = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(got.hex(), k)
    except Exception:
        return False
