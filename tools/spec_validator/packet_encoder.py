"""Independent encoders for deterministic Version 1 packet vectors."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .loader import VectorValidationError, load_json


PACKET_TYPES = {
    "AUDIO": 0x01,
    "PTT_ON": 0x02,
    "PTT_OFF": 0x03,
    "KEEPALIVE": 0x04,
    "JOIN": 0x05,
    "LEAVE": 0x06,
    "TALK_GRANT": 0x07,
    "TALK_RELEASE": 0x08,
    "TALK_DENY": 0x09,
    "KEY_EXCHANGE": 0x0A,
    "CODEC_CONFIG": 0x0B,
    "FEC": 0x0C,
    "SERVER_CONFIG": 0x0D,
    "PING": 0x0E,
    "PONG": 0x0F,
    "AUTH_HELLO": 0x10,
    "AUTH_CHALLENGE": 0x11,
    "IDENTITY_BEGIN": 0x12,
    "IDENTITY_CHALLENGE": 0x13,
    "IDENTITY_PROOF": 0x14,
    "IDENTITY_DENY": 0x15,
    "SERVICE_ADMISSION_BEGIN": 0x16,
    "SERVICE_ADMISSION_CHALLENGE": 0x17,
    "SERVICE_ADMISSION_PROOF": 0x18,
    "SERVICE_ADMISSION_DENY": 0x19,
    "PTT_REQUEST": 0x1A,
}

EMPTY_PAYLOAD_TYPES = {"PTT_ON"}


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


def encode_fixed_header(fields: Any) -> bytes:
    """Encode the Version 1 16-byte fixed envelope header."""
    if not isinstance(fields, dict):
        raise VectorValidationError("fields must be an object")

    packet_type = fields.get("type")
    if packet_type not in PACKET_TYPES:
        raise VectorValidationError(f"unknown packet type: {packet_type!r}")
    version = _integer(fields.get("version"), "fields.version", 0xFF)
    if version != 1:
        raise VectorValidationError("packet-envelope-v1 vectors must use version 1")
    header_length = _integer(fields.get("headerLen"), "fields.headerLen", 0xFFFF)
    if header_length != 16:
        raise VectorValidationError(
            "packet suite currently supports only the 16-byte fixed-header vectors"
        )
    return struct.pack(
        ">BBHIIHH",
        version,
        PACKET_TYPES[packet_type],
        header_length,
        _integer(fields.get("channelId"), "fields.channelId", 0xFFFFFFFF),
        _integer(fields.get("senderId"), "fields.senderId", 0xFFFFFFFF),
        _integer(fields.get("seq"), "fields.seq", 0xFFFF),
        _integer(fields.get("flags"), "fields.flags", 0xFFFF),
    )


def _encode_codec_config(config: Any) -> bytes:
    if not isinstance(config, dict):
        raise VectorValidationError("codecConfig must be an object")
    return struct.pack(
        ">BBIB12s",
        _integer(config.get("flags"), "codecConfig.flags", 0xFF),
        _integer(config.get("codecTransportId"), "codecConfig.codecTransportId", 0xFF),
        _integer(config.get("codecModeBps"), "codecConfig.codecModeBps", 0xFFFFFFFF),
        _integer(config.get("fecOptions"), "codecConfig.fecOptions", 0xFF),
        _hex_bytes(
            config.get("mediaNonceBase96Hex"),
            "codecConfig.mediaNonceBase96Hex",
            expected_length=12,
        ),
    )


def _encode_server_config(config: Any) -> bytes:
    if not isinstance(config, dict):
        raise VectorValidationError("serverConfig must be an object")
    multi_talk = config.get("multiTalkEnabled")
    if not isinstance(multi_talk, bool):
        raise VectorValidationError("serverConfig.multiTalkEnabled must be boolean")
    return struct.pack(
        ">HBBHH",
        _integer(config.get("maximumTalkSeconds"), "serverConfig.maximumTalkSeconds", 0xFFFF),
        int(multi_talk),
        _integer(
            config.get("maximumActiveTalkers"),
            "serverConfig.maximumActiveTalkers",
            0xFF,
        ),
        _integer(
            config.get("membershipLeaseSeconds"),
            "serverConfig.membershipLeaseSeconds",
            0xFFFF,
        ),
        _integer(
            config.get("keepaliveIntervalSeconds"),
            "serverConfig.keepaliveIntervalSeconds",
            0xFFFF,
        ),
    )


def encode_payload(vector: Any) -> bytes:
    """Encode a vector payload from semantic fixture fields, not payloadHex."""
    if not isinstance(vector, dict):
        raise VectorValidationError("packet vector must be an object")

    fields = vector.get("fields")
    packet_type = fields.get("type") if isinstance(fields, dict) else None
    if "codecConfig" in vector:
        if packet_type != "CODEC_CONFIG":
            raise VectorValidationError("codecConfig is valid only for CODEC_CONFIG")
        return _encode_codec_config(vector["codecConfig"])
    if "serverConfig" in vector:
        if packet_type != "SERVER_CONFIG":
            raise VectorValidationError("serverConfig is valid only for SERVER_CONFIG")
        return _encode_server_config(vector["serverConfig"])
    if "talkerId" in vector:
        if packet_type not in {"TALK_GRANT", "TALK_DENY", "TALK_RELEASE"}:
            raise VectorValidationError(
                "talkerId is valid only for TALK_GRANT, TALK_DENY, or TALK_RELEASE"
            )
        talker_id = _integer(vector["talkerId"], "talkerId", 0xFFFFFFFF)
        if packet_type == "TALK_RELEASE":
            return struct.pack(
                ">IB",
                talker_id,
                _integer(vector.get("releaseReason"), "releaseReason", 0xFF),
            )
        if "releaseReason" in vector:
            raise VectorValidationError("releaseReason is valid only for TALK_RELEASE")
        return struct.pack(">I", talker_id)
    if "pingNonceHex" in vector:
        if packet_type not in {"PING", "PONG"}:
            raise VectorValidationError("pingNonceHex is valid only for PING or PONG")
        return _hex_bytes(vector["pingNonceHex"], "pingNonceHex", expected_length=8)
    if "audioSeq" in vector:
        if packet_type is not None:
            raise VectorValidationError("audio payload vector must not include envelope fields")
        return struct.pack(">H", _integer(vector["audioSeq"], "audioSeq", 0xFFFF)) + _hex_bytes(
            vector.get("codecFrameHex"), "codecFrameHex"
        )
    if packet_type in EMPTY_PAYLOAD_TYPES:
        return b""
    raise VectorValidationError("vector has no independently encodable payload definition")


def _check_equal(case_name: str, label: str, actual: bytes, expected: bytes) -> str | None:
    if actual == expected:
        return None
    return (
        f"{case_name}: {label} mismatch; expected {expected.hex()}, "
        f"got {actual.hex()}"
    )


def validate_packet_envelope_vectors(root: Path) -> list[str]:
    """Validate every deterministic V1 envelope/payload fixture byte-for-byte."""
    vector_path = root / "test-vectors/packet-envelope-v1.json"
    try:
        document = load_json(vector_path)
    except VectorValidationError as exc:
        return [f"test-vectors/packet-envelope-v1.json: {exc}"]

    vectors = document.get("vectors") if isinstance(document, dict) else None
    if not isinstance(vectors, list):
        return ["test-vectors/packet-envelope-v1.json: vectors must be an array"]

    errors: list[str] = []
    for index, vector in enumerate(vectors):
        case_name = f"packet vector {index}"
        try:
            if not isinstance(vector, dict):
                raise VectorValidationError("vector must be an object")
            name = vector.get("name")
            if not isinstance(name, str) or not name:
                raise VectorValidationError("vector name must be a non-empty string")
            case_name = name
            if "payloadHex" not in vector and "datagramHex" not in vector:
                continue
            payload = encode_payload(vector)

            if "payloadHex" in vector:
                expected_payload = _hex_bytes(vector["payloadHex"], f"{name}.payloadHex")
                mismatch = _check_equal(name, "payload", payload, expected_payload)
                if mismatch:
                    errors.append(mismatch)

            if "datagramHex" in vector:
                header = encode_fixed_header(vector.get("fields"))
                expected_datagram = _hex_bytes(vector["datagramHex"], f"{name}.datagramHex")
                if len(expected_datagram) > 1200:
                    errors.append(f"{name}: datagram exceeds the 1200-byte UDP limit")
                mismatch = _check_equal(name, "datagram", header + payload, expected_datagram)
                if mismatch:
                    errors.append(mismatch)
        except VectorValidationError as exc:
            errors.append(f"{case_name}: {exc}")
    return errors
