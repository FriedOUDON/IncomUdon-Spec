"""Independent cryptographic verification for canonical specification vectors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
import unicodedata
from pathlib import Path
from typing import Any, Callable

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .loader import VectorValidationError, load_json


ARGON2ID_V1 = {
    "version": 19,
    "memoryKiB": 65536,
    "iterations": 3,
    "parallelism": 4,
    "outputBytes": 32,
}
CHANNEL_SALT_DOMAIN = b"incomudon-channel-password-salt-v1\0"
MEDIA_KEY_INFO = b"incomudon-session-aesgcm-v2"
CONTROL_KEY_INFO = b"incomudon-control-auth-v1"
DIRECTORY_CHANNEL_KEY_INFO = b"incomudon-directory-channel-v3"
DIRECTORY_C2R_KEY_INFO = b"incomudon-directory-channel-v3 client-to-relay"
DIRECTORY_R2C_KEY_INFO = b"incomudon-directory-channel-v3 relay-to-client"
DIRECTORY_EPOCH_KEY_INFO = b"incomudon-directory-envelope-v3"
CONTROL_TAG_DOMAIN = b"incomudon-control-auth-v1\0"
CONTROL_COOKIE_DOMAIN = b"incomudon-control-cookie-v1\0"
DIRECTORY_AAD_DOMAIN = b"IncomUdon Directory Envelope AAD v3\0"


def _integer(value: Any, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise VectorValidationError(f"{label} must be an integer in 0..{maximum}")
    return value


def _hex_bytes(value: Any, label: str, expected_length: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise VectorValidationError(f"{label} must be a hexadecimal string")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise VectorValidationError(f"{label} is not valid hexadecimal") from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise VectorValidationError(
            f"{label} must encode {expected_length} bytes, got {len(decoded)}"
        )
    return decoded


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise VectorValidationError(f"{label} must be a Base64URL string")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise VectorValidationError(f"{label} is not valid Base64URL") from exc


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """Expand HKDF-SHA-256 directly so the validator has no product dependency."""
    if not 0 < length <= 255 * hashlib.sha256().digest_size:
        raise VectorValidationError(f"invalid HKDF output length: {length}")
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    output = bytearray()
    previous = b""
    counter = 1
    while len(output) < length:
        previous = hmac.new(prk, previous + info + bytes([counter]), hashlib.sha256).digest()
        output.extend(previous)
        counter += 1
    return bytes(output[:length])


def _channel_salt(channel_id: int) -> bytes:
    return hashlib.sha256(CHANNEL_SALT_DOMAIN + struct.pack(">I", channel_id)).digest()[:16]


def _compare(errors: list[str], label: str, actual: bytes | str | int, expected: bytes | str | int) -> None:
    if actual == expected:
        return
    if isinstance(actual, bytes) and isinstance(expected, bytes):
        errors.append(f"{label}: expected {expected.hex()}, got {actual.hex()}")
        return
    errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def _validate_argon2_parameters(parameters: Any, label: str) -> None:
    if not isinstance(parameters, dict):
        raise VectorValidationError(f"{label} must be an object")
    for name, expected in ARGON2ID_V1.items():
        if parameters.get(name) != expected:
            raise VectorValidationError(
                f"{label}.{name} must be the argon2id-v1 value {expected}"
            )


class CredentialDeriver:
    """Caches expensive Argon2id derivations shared by multiple vectors."""

    def __init__(self) -> None:
        self._argon2_cache: dict[tuple[bytes, bytes], bytes] = {}

    def argon2id_v1(self, passphrase: str, salt: bytes) -> bytes:
        password = unicodedata.normalize("NFC", passphrase).encode("utf-8")
        cache_key = (password, salt)
        if cache_key not in self._argon2_cache:
            self._argon2_cache[cache_key] = hash_secret_raw(
                secret=password,
                salt=salt,
                time_cost=ARGON2ID_V1["iterations"],
                memory_cost=ARGON2ID_V1["memoryKiB"],
                parallelism=ARGON2ID_V1["parallelism"],
                hash_len=ARGON2ID_V1["outputBytes"],
                type=Type.ID,
                version=ARGON2ID_V1["version"],
            )
        return self._argon2_cache[cache_key]

    def derive(self, kind: str, vector: dict[str, Any], salt: bytes) -> bytes:
        if kind == "argon2id-v1":
            password = vector.get("passwordInput")
            if not isinstance(password, str):
                raise VectorValidationError("argon2id-v1 vector requires passwordInput")
            return self.argon2id_v1(password, salt)
        if kind == "raw-secret-v1":
            credential = vector.get("credentialInput")
            if not isinstance(credential, str) or not credential.startswith("secret:"):
                raise VectorValidationError("raw-secret-v1 vector requires a secret: credentialInput")
            secret = _hex_bytes(credential[len("secret:") :], "raw-secret credential", 32)
            return _hkdf_sha256(secret, salt, b"incomudon-raw-secret-v1", 32)
        raise VectorValidationError(f"unsupported credential kind: {kind!r}")


def _load(root: Path, relative: str) -> dict[str, Any]:
    value = load_json(root / relative)
    if not isinstance(value, dict):
        raise VectorValidationError(f"{relative} must contain an object")
    return value


def _validate_password_kdf(root: Path, deriver: CredentialDeriver) -> list[str]:
    document = _load(root, "test-vectors/password-kdf-v1.json")
    _validate_argon2_parameters(document.get("argon2idV1"), "password-kdf argon2idV1")
    vectors = document.get("vectors")
    if not isinstance(vectors, list):
        raise VectorValidationError("password-kdf vectors must be an array")

    errors: list[str] = []
    for index, vector in enumerate(vectors):
        if not isinstance(vector, dict):
            errors.append(f"password-kdf vector {index}: must be an object")
            continue
        name = vector.get("name", f"password-kdf vector {index}")
        try:
            if vector.get("expected") == "reject":
                credential = vector.get("credentialInput")
                if not isinstance(credential, str) or not credential.startswith("sha256:"):
                    raise VectorValidationError("removed credential case must use sha256: input")
                continue
            if "expectedCredentialKind" in vector:
                credential = vector.get("credentialInput")
                if not isinstance(credential, str):
                    raise VectorValidationError("credential classification case requires credentialInput")
                actual_kind = "raw-secret-v1" if credential.startswith("secret:") else "argon2id-v1"
                _compare(errors, f"{name} credential kind", actual_kind, vector["expectedCredentialKind"])
                continue

            channel_id = _integer(vector.get("channelId"), f"{name}.channelId", 0xFFFFFFFF)
            salt = _channel_salt(channel_id)
            _compare(
                errors,
                f"{name} channel salt",
                salt,
                _hex_bytes(vector.get("channelSaltHex"), f"{name}.channelSaltHex", 16),
            )
            kind = vector.get("credentialKind")
            if not isinstance(kind, str):
                raise VectorValidationError("credential vector requires credentialKind")
            password_key = deriver.derive(kind, vector, salt)
            _compare(
                errors,
                f"{name} password key",
                password_key,
                _hex_bytes(vector.get("passwordKeyHex"), f"{name}.passwordKeyHex", 32),
            )
            media_key = _hkdf_sha256(password_key, b"", MEDIA_KEY_INFO, 32)
            _compare(
                errors,
                f"{name} media key",
                media_key,
                _hex_bytes(vector.get("mediaKeyHex"), f"{name}.mediaKeyHex", 32),
            )
        except VectorValidationError as exc:
            errors.append(f"{name}: {exc}")
    return errors


def _validate_aes_gcm_v2(root: Path, deriver: CredentialDeriver) -> list[str]:
    document = _load(root, "test-vectors/aes-gcm-v2.json")
    _validate_argon2_parameters(document.get("argon2id"), "aes-gcm-v2 argon2id")
    errors: list[str] = []
    channel_id = _integer(document.get("channelId"), "aes-gcm-v2 channelId", 0xFFFFFFFF)
    salt = _channel_salt(channel_id)
    _compare(errors, "aes-gcm-v2 channel salt", salt, _hex_bytes(document.get("channelSaltHex"), "channelSaltHex", 16))
    password_key = deriver.derive(document.get("credentialKind"), document, salt)
    _compare(errors, "aes-gcm-v2 password key", password_key, _hex_bytes(document.get("passwordKeyHex"), "passwordKeyHex", 32))
    key = _hkdf_sha256(password_key, b"", MEDIA_KEY_INFO, 32)
    _compare(errors, "aes-gcm-v2 media key", key, _hex_bytes(document.get("keyHex"), "keyHex", 32))

    packet = document.get("packet")
    if not isinstance(packet, dict) or packet.get("type") != "AUDIO":
        raise VectorValidationError("aes-gcm-v2 packet must be an AUDIO object")
    base = _hex_bytes(packet.get("mediaNonceBase96Hex"), "mediaNonceBase96Hex", 12)
    counter = _integer(packet.get("mediaCounter"), "mediaCounter", 0xFFFFFFFF)
    nonce_value = int.from_bytes(base, "big") + counter
    if nonce_value >= 1 << 96:
        raise VectorValidationError("media nonce overflows 96 bits")
    nonce = nonce_value.to_bytes(12, "big")
    _compare(errors, "aes-gcm-v2 nonce", nonce, _hex_bytes(packet.get("derivedNonce96Hex"), "derivedNonce96Hex", 12))
    header = struct.pack(
        ">BBHIIHH12sII",
        1,
        0x01,
        _integer(packet.get("headerLen"), "headerLen", 0xFFFF),
        channel_id,
        _integer(packet.get("senderId"), "senderId", 0xFFFFFFFF),
        _integer(packet.get("seq"), "seq", 0xFFFF),
        _integer(packet.get("flags"), "flags", 0xFFFF),
        base,
        counter,
        _integer(document.get("mediaKeyId"), "mediaKeyId", 0xFFFFFFFF),
    )
    aad = _hex_bytes(document.get("aadHex"), "aadHex")
    _compare(errors, "aes-gcm-v2 AAD", header, aad)
    plaintext = _hex_bytes(document.get("plaintextHex"), "plaintextHex")
    encrypted = AESGCM(key).encrypt(nonce, plaintext, header)
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    _compare(errors, "aes-gcm-v2 ciphertext", ciphertext, _hex_bytes(document.get("ciphertextHex"), "ciphertextHex"))
    _compare(errors, "aes-gcm-v2 tag", tag, _hex_bytes(document.get("tagHex"), "tagHex", 16))
    datagram = header + encrypted
    _compare(errors, "aes-gcm-v2 datagram", datagram, _hex_bytes(document.get("datagramHex"), "datagramHex"))

    negative = document.get("negativeCase")
    if not isinstance(negative, dict):
        raise VectorValidationError("aes-gcm-v2 negativeCase must be an object")
    offset = _integer(negative.get("mutateOffset"), "negativeCase.mutateOffset", len(datagram) - 1)
    xor = _hex_bytes(negative.get("xor"), "negativeCase.xor", 1)[0]
    mutated = bytearray(datagram)
    mutated[offset] ^= xor
    try:
        AESGCM(key).decrypt(nonce, bytes(mutated[36:]), bytes(mutated[:36]))
    except InvalidTag:
        pass
    else:
        errors.append("aes-gcm-v2 mutated datagram unexpectedly authenticates")
    return errors


def _validate_control_auth(root: Path, deriver: CredentialDeriver) -> list[str]:
    document = _load(root, "test-vectors/control-auth-v1.json")
    _validate_argon2_parameters(document.get("argon2id"), "control-auth-v1 argon2id")
    errors: list[str] = []
    channel_id = _integer(document.get("channelId"), "control-auth-v1 channelId", 0xFFFFFFFF)
    salt = _channel_salt(channel_id)
    _compare(errors, "control-auth-v1 channel salt", salt, _hex_bytes(document.get("channelSaltHex"), "channelSaltHex", 16))
    password_key = deriver.derive(document.get("credentialKind"), document, salt)
    _compare(errors, "control-auth-v1 password key", password_key, _hex_bytes(document.get("passwordKeyHex"), "passwordKeyHex", 32))
    media_key = _hkdf_sha256(password_key, b"", MEDIA_KEY_INFO, 32)
    control_key = _hkdf_sha256(password_key, b"", CONTROL_KEY_INFO, 32)
    _compare(errors, "control-auth-v1 media key", media_key, _hex_bytes(document.get("mediaKeyHex"), "mediaKeyHex", 32))
    _compare(errors, "control-auth-v1 control key", control_key, _hex_bytes(document.get("controlKeyHex"), "controlKeyHex", 32))

    packet = document.get("controlPacket")
    if not isinstance(packet, dict):
        raise VectorValidationError("controlPacket must be an object")
    header = _hex_bytes(packet.get("headerHex"), "controlPacket.headerHex", 28)
    payload = _hex_bytes(packet.get("payloadHex"), "controlPacket.payloadHex")
    domain = _hex_bytes(packet.get("domainHex"), "controlPacket.domainHex")
    _compare(errors, "control-auth-v1 domain", domain, CONTROL_TAG_DOMAIN)
    tag = hmac.new(control_key, domain + header + payload, hashlib.sha256).digest()[:16]
    _compare(errors, "control-auth-v1 tag", tag, _hex_bytes(packet.get("tagHex"), "controlPacket.tagHex", 16))

    cookie_case = document.get("cookieCase")
    if not isinstance(cookie_case, dict):
        raise VectorValidationError("cookieCase must be an object")
    cookie_input = (
        CONTROL_COOKIE_DOMAIN
        + _hex_bytes(cookie_case.get("sourceIp16Hex"), "sourceIp16Hex", 16)
        + struct.pack(">H", _integer(cookie_case.get("sourcePort"), "sourcePort", 0xFFFF))
        + header[4:8]
        + header[8:12]
        + header[24:28]
        + struct.pack(">I", _integer(cookie_case.get("clientSessionId"), "clientSessionId", 0xFFFFFFFF))
        + struct.pack(">I", _integer(cookie_case.get("expiryUnixSeconds"), "expiryUnixSeconds", 0xFFFFFFFF))
    )
    cookie = hmac.new(
        _hex_bytes(cookie_case.get("relayCookieSecretHex"), "relayCookieSecretHex", 32),
        cookie_input,
        hashlib.sha256,
    ).digest()[:16]
    _compare(errors, "control-auth-v1 cookie", cookie, _hex_bytes(cookie_case.get("cookieHex"), "cookieHex", 16))
    return errors


def _directory_aad(fixture: dict[str, Any]) -> bytes:
    packet_type = fixture.get("type")
    if not isinstance(packet_type, str):
        raise VectorValidationError("Directory fixture type must be a string")
    envelope = fixture.get("envelope")
    if not isinstance(envelope, dict):
        raise VectorValidationError("Directory fixture envelope must be an object")
    return (
        DIRECTORY_AAD_DOMAIN
        + bytes([_integer(envelope.get("v"), "Directory envelope v", 0xFF)])
        + bytes([_integer(fixture.get("transportBinding"), "transportBinding", 0xFF)])
        + bytes([len(packet_type.encode("ascii"))])
        + packet_type.encode("ascii")
        + struct.pack(">I", _integer(envelope.get("channelId"), "Directory channelId", 0xFFFFFFFF))
        + _hex_bytes(fixture.get("epochRawHex"), "Directory epochRawHex", 16)
        + struct.pack(">Q", _integer(fixture.get("sequence"), "Directory sequence", (1 << 53) - 1))
        + struct.pack(">Q", _integer(fixture.get("expiresAt"), "Directory expiresAt", (1 << 53) - 1))
    )


def _directory_datagram(fixture: dict[str, Any], ciphertext: str) -> bytes:
    envelope = fixture["envelope"]
    canonical = {
        "v": envelope["v"],
        "type": fixture["type"],
        "channelId": envelope["channelId"],
        "epoch": fixture["epochBase64Url"],
        "sequence": fixture["sequence"],
        "expiresAt": fixture["expiresAt"],
        "ciphertext": ciphertext,
    }
    return json.dumps(canonical, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _validate_directory_fixture(
    errors: list[str], directory_channel_key: bytes, label: str, fixture: dict[str, Any]
) -> None:
    packet_type = fixture.get("type")
    if packet_type in {"request", "register", "heartbeat"}:
        directional_info = DIRECTORY_C2R_KEY_INFO
    elif packet_type in {"snapshot", "participants", "error"}:
        directional_info = DIRECTORY_R2C_KEY_INFO
    else:
        raise VectorValidationError(f"{label}: unsupported Directory type {packet_type!r}")
    directional_key = _hkdf_sha256(directory_channel_key, b"", directional_info, 32)
    epoch = _hex_bytes(fixture.get("epochRawHex"), f"{label}.epochRawHex", 16)
    _compare(errors, f"{label} epoch Base64URL", _base64url(epoch), fixture.get("epochBase64Url"))
    epoch_key = _hkdf_sha256(directional_key, epoch, DIRECTORY_EPOCH_KEY_INFO, 32)
    sequence = _integer(fixture.get("sequence"), f"{label}.sequence", (1 << 53) - 1)
    nonce = b"IDP3" + struct.pack(">Q", sequence)
    _compare(errors, f"{label} nonce", nonce, _hex_bytes(fixture.get("nonce12Hex"), f"{label}.nonce12Hex", 12))
    aad = _directory_aad(fixture)
    _compare(errors, f"{label} AAD", aad, _hex_bytes(fixture.get("aadHex"), f"{label}.aadHex"))
    encrypted = AESGCM(epoch_key).encrypt(nonce, fixture.get("plaintextUtf8", "").encode("utf-8"), aad)
    ciphertext = _base64url(encrypted)
    _compare(errors, f"{label} ciphertext", ciphertext, fixture.get("ciphertextBase64Url"))
    envelope = fixture.get("envelope")
    if not isinstance(envelope, dict):
        raise VectorValidationError(f"{label}.envelope must be an object")
    _compare(errors, f"{label} envelope ciphertext", ciphertext, envelope.get("ciphertext"))
    datagram = _directory_datagram(fixture, ciphertext)
    _compare(errors, f"{label} datagram", datagram, fixture.get("datagramUtf8", "").encode("utf-8"))
    _compare(errors, f"{label} datagram byte length", len(datagram), fixture.get("datagramBytes"))
    if "carrierHex" in fixture:
        carrier = b"IDP3\x01" + datagram
        _compare(errors, f"{label} media-port carrier", carrier, _hex_bytes(fixture.get("carrierHex"), f"{label}.carrierHex"))
        _compare(errors, f"{label} carrier byte length", len(carrier), fixture.get("carrierBytes"))


def _validate_directory_v3(root: Path) -> list[str]:
    document = _load(root, "test-vectors/directory-v3.json")
    crypto = document.get("crypto")
    if not isinstance(crypto, dict):
        raise VectorValidationError("Directory v3 crypto must be an object")
    errors: list[str] = []
    password_key = _hex_bytes(crypto.get("passwordKeyHex"), "Directory passwordKeyHex", 32)
    directory_channel_key = _hkdf_sha256(password_key, b"", DIRECTORY_CHANNEL_KEY_INFO, 32)
    _compare(
        errors,
        "Directory v3 channel key",
        directory_channel_key,
        _hex_bytes(crypto.get("directoryChannelKeyHex"), "Directory directoryChannelKeyHex", 32),
    )
    dedicated = crypto.get("dedicatedRequest")
    media_request = crypto.get("mediaPortRequest")
    fragments = crypto.get("mediaPortParticipantsFragments")
    if not isinstance(dedicated, dict) or not isinstance(media_request, dict) or not isinstance(fragments, list):
        raise VectorValidationError("Directory v3 crypto fixtures are malformed")
    _validate_directory_fixture(errors, directory_channel_key, "Directory dedicated request", dedicated)
    _validate_directory_fixture(errors, directory_channel_key, "Directory media-port request", media_request)
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict):
            raise VectorValidationError(f"Directory media-port fragment {index} must be an object")
        _validate_directory_fixture(
            errors,
            directory_channel_key,
            f"Directory media-port fragment {index}",
            fragment,
        )
    return errors


def _validate_key_pair(errors: list[str], label: str, seed_hex: Any, public_hex: Any) -> tuple[Ed25519PrivateKey, bytes]:
    seed = _hex_bytes(seed_hex, f"{label} private seed", 32)
    expected_public = _hex_bytes(public_hex, f"{label} public key", 32)
    private = Ed25519PrivateKey.from_private_bytes(seed)
    actual_public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    _compare(errors, f"{label} public key", actual_public, expected_public)
    return private, expected_public


def _validate_jws(
    errors: list[str], label: str, jws: Any, issuer_private: Ed25519PrivateKey, issuer_public: bytes
) -> str:
    if not isinstance(jws, dict):
        raise VectorValidationError(f"{label} JWS must be an object")
    protected = jws.get("protected_header_json")
    payload = jws.get("payload_json")
    if not isinstance(protected, str) or not isinstance(payload, str):
        raise VectorValidationError(f"{label} JWS requires JSON strings")
    signing_input = _base64url(protected.encode("utf-8")) + "." + _base64url(payload.encode("utf-8"))
    _compare(errors, f"{label} JWS signing input", signing_input, jws.get("signing_input_ascii"))
    signature = issuer_private.sign(signing_input.encode("ascii"))
    _compare(errors, f"{label} JWS signature", _base64url(signature), jws.get("signature_base64url"))
    compact = signing_input + "." + _base64url(signature)
    _compare(errors, f"{label} compact JWS", compact, jws.get("compact_jws"))
    _compare(errors, f"{label} compact JWS byte length", len(compact.encode("ascii")), jws.get("byte_length"))
    try:
        Ed25519PublicKey.from_public_bytes(issuer_public).verify(signature, signing_input.encode("ascii"))
    except InvalidSignature as exc:
        raise VectorValidationError(f"{label} JWS signature does not verify") from exc
    return compact


def _validate_admission(
    root: Path,
    relative: str,
    label: str,
    jws_name: str,
    subject_key_name: str,
    flow_prefix: str,
    jws_length_key: str,
    domain: bytes,
) -> list[str]:
    document = _load(root, relative)
    keys = document.get("synthetic_keys")
    if not isinstance(keys, dict):
        raise VectorValidationError(f"{label} synthetic_keys must be an object")
    errors: list[str] = []
    issuer_private, issuer_public = _validate_key_pair(
        errors,
        f"{label} issuer",
        keys.get("issuer_private_seed_hex"),
        keys.get("issuer_public_key_hex"),
    )
    subject_private, subject_public = _validate_key_pair(
        errors,
        f"{label} subject",
        keys.get(f"{subject_key_name}_private_seed_hex"),
        keys.get(f"{subject_key_name}_public_key_hex"),
    )
    public_digest = _base64url(hashlib.sha256(subject_public).digest())
    _compare(errors, f"{label} subject key digest", public_digest, keys.get(f"{subject_key_name}_public_key_sha256_base64url"))

    jws = document.get(jws_name)
    compact = _validate_jws(errors, label, jws, issuer_private, issuer_public)
    if not isinstance(jws, dict):
        raise VectorValidationError(f"{label} JWS must be an object")
    try:
        claims = json.loads(jws["payload_json"])
    except json.JSONDecodeError as exc:
        raise VectorValidationError(f"{label} JWS payload JSON is invalid") from exc
    if not isinstance(claims, dict):
        raise VectorValidationError(f"{label} JWS claims must be an object")
    channel_id = _integer(claims.get("ch"), f"{label} claims ch", 0xFFFFFFFF)
    sender_id = _integer(claims.get("sid"), f"{label} claims sid", 0xFFFFFFFF)

    challenge = document.get(f"{flow_prefix}_challenge")
    proof = document.get(f"{flow_prefix}_proof")
    if not isinstance(challenge, dict) or not isinstance(proof, dict):
        raise VectorValidationError(f"{label} challenge/proof fixtures must be objects")
    challenge_bytes = _hex_bytes(challenge.get("challenge_hex"), f"{label} challenge", 32)
    message = hashlib.sha256(
        domain
        + challenge_bytes
        + struct.pack(">II", channel_id, sender_id)
        + hashlib.sha256(compact.encode("ascii")).digest()
    ).digest()
    _compare(errors, f"{label} proof message hash", message, _hex_bytes(proof.get("message_sha256_hex"), f"{label} proof message", 32))
    proof_signature = subject_private.sign(message)
    _compare(errors, f"{label} proof signature", proof_signature, _hex_bytes(proof.get("signature_hex"), f"{label} proof signature", 64))
    try:
        Ed25519PublicKey.from_public_bytes(subject_public).verify(proof_signature, message)
    except InvalidSignature as exc:
        raise VectorValidationError(f"{label} proof signature does not verify") from exc

    begin = document.get(f"{flow_prefix}_begin")
    if not isinstance(begin, dict):
        raise VectorValidationError(f"{label} begin fixture must be an object")
    begin_payload = struct.pack(">H", len(compact.encode("ascii"))) + compact.encode("ascii") + subject_public
    _compare(errors, f"{label} begin payload", begin_payload, _hex_bytes(begin.get("payload_hex"), f"{label} begin payload"))
    _compare(errors, f"{label} begin JWS length", len(compact.encode("ascii")), begin.get(jws_length_key))
    _compare(errors, f"{label} authenticated begin byte length", 28 + len(begin_payload) + 16, begin.get("authenticated_datagram_bytes"))

    challenge_payload = struct.pack(">I", _integer(challenge.get("expiry_unix_seconds"), f"{label} challenge expiry", 0xFFFFFFFF)) + challenge_bytes
    _compare(errors, f"{label} challenge payload", challenge_payload, _hex_bytes(challenge.get("payload_hex"), f"{label} challenge payload"))
    denies = document.get(f"{flow_prefix}_deny_payloads")
    if not isinstance(denies, list):
        raise VectorValidationError(f"{label} deny payloads must be an array")
    for index, denial in enumerate(denies):
        if not isinstance(denial, dict):
            raise VectorValidationError(f"{label} deny payload {index} must be an object")
        expected = _hex_bytes(denial.get("payload_hex"), f"{label} deny payload {index}")
        actual = bytes([_integer(denial.get("reason_byte"), f"{label} deny reason {index}", 0xFF)])
        _compare(errors, f"{label} deny payload {index}", actual, expected)
    return errors


def _validate_identity_admission(root: Path) -> list[str]:
    return _validate_admission(
        root,
        "test-vectors/identity-admission-v1.json",
        "Identity Admission",
        "ticket",
        "client",
        "identity",
        "ticket_length",
        b"incomudon-identity-admission-v1\0",
    )


def _validate_service_admission(root: Path) -> list[str]:
    return _validate_admission(
        root,
        "test-vectors/management/service-admission-v1.json",
        "Managed Service Admission",
        "grant",
        "service",
        "service_admission",
        "grant_length",
        b"incomudon-managed-service-admission-v1\0",
    )


def validate_crypto_vectors(root: Path) -> list[str]:
    """Recompute all crypto golden values without importing product code."""
    deriver = CredentialDeriver()
    validators: list[tuple[str, Callable[[], list[str]]]] = [
        ("password KDF", lambda: _validate_password_kdf(root, deriver)),
        ("AES-GCM v2", lambda: _validate_aes_gcm_v2(root, deriver)),
        ("Control Authentication v1", lambda: _validate_control_auth(root, deriver)),
        ("Directory UDP v3", lambda: _validate_directory_v3(root)),
        ("Identity Admission v1", lambda: _validate_identity_admission(root)),
        ("Managed Service Admission v1", lambda: _validate_service_admission(root)),
    ]
    errors: list[str] = []
    for label, validator in validators:
        try:
            errors.extend(validator())
        except (VectorValidationError, ValueError, struct.error) as exc:
            errors.append(f"{label}: {exc}")
    return errors
