"""Sealing: the case truth at rest.

Threat model
------------
The adversary is *you at 1am, curious and weak*. Not a cryptographer. The seal
exists to make peeking a deliberate act rather than an accident — you cannot
open `case.sealed` in an editor, you cannot grep it, and an LLM reading the
repo will not stumble onto the culprit while looking for something else.

Anyone with the key file can decrypt, and the key file sits next to the case.
That is on purpose: this is a lock on a diary, not a safe. What it buys is that
peeking requires typing `mystery spoil`, which writes to `spoilers.log`, so the
final score stays honest.

Construction: HMAC-SHA256 in counter mode for the keystream, encrypt-then-MAC
with a separate HMAC key. Standard, stdlib-only, no dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct

MAGIC = b"MYST1\x00"
KEY_LEN = 32


def new_key() -> bytes:
    return os.urandom(KEY_LEN)


def _subkeys(key: bytes, nonce: bytes) -> tuple[bytes, bytes]:
    """Derive independent encryption and authentication keys."""
    enc = hmac.new(key, b"enc" + nonce, hashlib.sha256).digest()
    mac = hmac.new(key, b"mac" + nonce, hashlib.sha256).digest()
    return enc, mac


def _keystream(enc_key: bytes, nonce: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hmac.new(enc_key, nonce + struct.pack(">Q", counter), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(16)
    enc_key, mac_key = _subkeys(key, nonce)
    ct = bytes(a ^ b for a, b in zip(plaintext, _keystream(enc_key, nonce, len(plaintext))))
    body = MAGIC + nonce + ct
    tag = hmac.new(mac_key, body, hashlib.sha256).digest()
    return body + tag


def decrypt(key: bytes, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("not a sealed case file")
    body, tag = blob[:-32], blob[-32:]
    nonce = body[len(MAGIC) : len(MAGIC) + 16]
    ct = body[len(MAGIC) + 16 :]
    enc_key, mac_key = _subkeys(key, nonce)
    if not hmac.compare_digest(hmac.new(mac_key, body, hashlib.sha256).digest(), tag):
        raise ValueError("sealed case failed integrity check — it was edited or the key is wrong")
    return bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct))))


# -- on-disk layout --------------------------------------------------------


class SealedCase:
    """A case directory: sealed truth + key + play state.

    cases/<slug>/
        case.sealed     encrypted Case JSON
        seal.key        the key (gitignored, mode 0600)
        state.json      what the player has found (readable, no spoilers)
        spoilers.log    append-only record of every peek
    """

    def __init__(self, case_dir: str):
        self.dir = case_dir
        self.sealed_path = os.path.join(case_dir, "case.sealed")
        self.key_path = os.path.join(case_dir, "seal.key")
        self.state_path = os.path.join(case_dir, "state.json")
        self.spoiler_path = os.path.join(case_dir, "spoilers.log")

    def exists(self) -> bool:
        return os.path.exists(self.sealed_path) and os.path.exists(self.key_path)

    def seal(self, case_json: str) -> None:
        os.makedirs(self.dir, exist_ok=True)
        key = new_key()
        with open(self.sealed_path, "wb") as fh:
            fh.write(encrypt(key, case_json.encode("utf-8")))
        fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)

    def open_case(self) -> dict:
        with open(self.key_path, "rb") as fh:
            key = fh.read()
        with open(self.sealed_path, "rb") as fh:
            return json.loads(decrypt(key, fh.read()))

    def record_spoiler(self, what: str, timestamp: str) -> None:
        with open(self.spoiler_path, "a", encoding="utf-8") as fh:
            fh.write(f"{timestamp}\t{what}\n")

    def spoiler_count(self) -> int:
        if not os.path.exists(self.spoiler_path):
            return 0
        with open(self.spoiler_path, "r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
