"""Independent GF(256) FEC parity and recovery validation."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .loader import VectorValidationError, load_json


PRIMITIVE_POLYNOMIAL = 0x11D
MAX_BLOCK_SIZE = 6


def _integer(value: Any, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise VectorValidationError(f"{label} must be an integer in 0..{maximum}")
    return value


def _hex_bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise VectorValidationError(f"{label} must be a hexadecimal string")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise VectorValidationError(f"{label} is not valid hexadecimal") from exc


def _xor(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise VectorValidationError("FEC operands must have equal padded lengths")
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def gf_mul(left: int, right: int) -> int:
    """Multiply two GF(256) elements with primitive polynomial 0x11d."""
    product = 0
    while right:
        if right & 1:
            product ^= left
        left <<= 1
        if left & 0x100:
            left ^= PRIMITIVE_POLYNOMIAL
        right >>= 1
    return product


def gf_pow(base: int, exponent: int) -> int:
    product = 1
    while exponent:
        if exponent & 1:
            product = gf_mul(product, base)
        base = gf_mul(base, base)
        exponent >>= 1
    return product


def gf_inv(value: int) -> int:
    if value == 0:
        raise VectorValidationError("zero has no GF(256) inverse")
    return gf_pow(value, 254)


def _gf_scale(data: bytes, coefficient: int) -> bytes:
    return bytes(gf_mul(value, coefficient) for value in data)


def _coefficients(block_size: int) -> list[int]:
    return [gf_pow(2, index) for index in range(block_size)]


def encode_parity(frames: list[bytes]) -> tuple[bytes, bytes]:
    """Return P and Q for non-empty padded frames in one FEC block."""
    if not 1 <= len(frames) <= MAX_BLOCK_SIZE:
        raise VectorValidationError("FEC block size must be 1 through 6")
    width = len(frames[0])
    if width == 0 or any(len(frame) != width for frame in frames):
        raise VectorValidationError("FEC frames must be non-empty and equally padded")
    p = bytes(width)
    q = bytes(width)
    for coefficient, frame in zip(_coefficients(len(frames)), frames, strict=True):
        p = _xor(p, frame)
        q = _xor(q, _gf_scale(frame, coefficient))
    return p, q


def recover_frames(
    padded_frames: list[bytes | None], p: bytes, q: bytes, lengths: list[int]
) -> list[bytes]:
    """Recover up to two padded frames and truncate to their advertised lengths."""
    if len(padded_frames) != len(lengths):
        raise VectorValidationError("FEC frame/length cardinality mismatch")
    if not padded_frames:
        raise VectorValidationError("FEC recovery block is empty")
    width = len(p)
    if len(q) != width:
        raise VectorValidationError("FEC parity lengths differ")
    missing = [index for index, frame in enumerate(padded_frames) if frame is None]
    if len(missing) > 2:
        raise VectorValidationError("more than two missing FEC frames are not recoverable")
    known_p = bytes(width)
    known_q = bytes(width)
    coefficients = _coefficients(len(padded_frames))
    for index, frame in enumerate(padded_frames):
        if frame is None:
            continue
        if len(frame) != width:
            raise VectorValidationError("received FEC frame has an invalid padded length")
        known_p = _xor(known_p, frame)
        known_q = _xor(known_q, _gf_scale(frame, coefficients[index]))
    residual_p = _xor(p, known_p)
    residual_q = _xor(q, known_q)

    if len(missing) == 1:
        padded_frames[missing[0]] = residual_p
    elif len(missing) == 2:
        first, second = missing
        first_coefficient = coefficients[first]
        second_coefficient = coefficients[second]
        divisor = first_coefficient ^ second_coefficient
        second_frame = _gf_scale(
            _xor(residual_q, _gf_scale(residual_p, first_coefficient)),
            gf_inv(divisor),
        )
        padded_frames[first] = _xor(residual_p, second_frame)
        padded_frames[second] = second_frame

    recovered: list[bytes] = []
    for frame, length in zip(padded_frames, lengths, strict=True):
        if frame is None:
            raise VectorValidationError("FEC recovery left a missing frame")
        if not 1 <= length <= len(frame):
            raise VectorValidationError("FEC advertised frame length is invalid")
        recovered.append(frame[:length])
    return recovered


def _compare(errors: list[str], label: str, actual: bytes | list[int], expected: bytes | list[int]) -> None:
    if actual == expected:
        return
    if isinstance(actual, bytes) and isinstance(expected, bytes):
        errors.append(f"{label}: expected {expected.hex()}, got {actual.hex()}")
    else:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def _member_sequences(block_start: int, block_size: int) -> list[int]:
    return [(block_start + index) & 0xFFFF for index in range(block_size)]


def _validate_block(
    errors: list[str], label: str, block: dict[str, Any], max_frame_bytes: int, fec_v2: bool
) -> None:
    block_start = _integer(block.get("blockStart"), f"{label}.blockStart", 0xFFFF)
    block_size = _integer(block.get("blockSize"), f"{label}.blockSize", MAX_BLOCK_SIZE)
    if block_size == 0:
        raise VectorValidationError(f"{label}.blockSize must be at least one")
    frames_value = block.get("frames")
    parity_value = block.get("parity")
    if not isinstance(frames_value, list) or not isinstance(parity_value, list):
        raise VectorValidationError(f"{label} frames and parity must be arrays")
    if len(frames_value) != block_size:
        raise VectorValidationError(f"{label} frame count does not match blockSize")
    if len(parity_value) != 2:
        raise VectorValidationError(f"{label} must contain P and Q parity")

    sequences = _member_sequences(block_start, block_size)
    frames: list[bytes] = []
    lengths: list[int] = []
    for index, frame_value in enumerate(frames_value):
        if not isinstance(frame_value, dict):
            raise VectorValidationError(f"{label} frame {index} must be an object")
        sequence = _integer(frame_value.get("audioSeq"), f"{label} frame {index} audioSeq", 0xFFFF)
        _compare(errors, f"{label} frame {index} modular audioSeq", [sequence], [sequences[index]])
        frame = _hex_bytes(frame_value.get("dataHex"), f"{label} frame {index} dataHex")
        if not 1 <= len(frame) <= max_frame_bytes:
            raise VectorValidationError(f"{label} frame {index} has invalid length {len(frame)}")
        frames.append(frame)
        lengths.append(len(frame))
    width = max(lengths)
    padded = [frame.ljust(width, b"\0") for frame in frames]
    expected_p, expected_q = encode_parity(padded)
    parity: dict[int, bytes] = {}
    for index, parity_value_item in enumerate(parity_value):
        if not isinstance(parity_value_item, dict):
            raise VectorValidationError(f"{label} parity {index} must be an object")
        parity_index = _integer(parity_value_item.get("parityIndex"), f"{label} parity index", 1)
        if parity_index in parity:
            raise VectorValidationError(f"{label} duplicates parity index {parity_index}")
        parity_data = _hex_bytes(parity_value_item.get("dataHex"), f"{label} parity {parity_index} dataHex")
        parity[parity_index] = parity_data
        expected = expected_p if parity_index == 0 else expected_q
        _compare(errors, f"{label} parity {parity_index}", parity_data, expected)
        if fec_v2:
            payload = (
                struct.pack(">BHBB", 2, block_start, block_size, parity_index)
                + b"".join(struct.pack(">H", length) for length in lengths)
                + expected
            )
            _compare(
                errors,
                f"{label} parity {parity_index} payload",
                payload,
                _hex_bytes(parity_value_item.get("fecPayloadHex"), f"{label} parity payload"),
            )
    if set(parity) != {0, 1}:
        raise VectorValidationError(f"{label} must contain parity indexes 0 and 1")

    recovery_cases = block.get("recoveryCases") if fec_v2 else [block.get("recoveryCase")]
    if not isinstance(recovery_cases, list):
        raise VectorValidationError(f"{label} recovery cases must be an array")
    source_by_sequence = dict(zip(sequences, frames, strict=True))
    for recovery_index, recovery_case in enumerate(recovery_cases):
        recovery_label = f"{label} recovery {recovery_index}"
        if not isinstance(recovery_case, dict):
            raise VectorValidationError(f"{recovery_label} must be an object")
        received = recovery_case.get("receivedSequences")
        missing = recovery_case.get("missingSequences")
        expected_output = recovery_case.get("expectedOutputSequences")
        if not isinstance(received, list) or not isinstance(missing, list) or not isinstance(expected_output, list):
            raise VectorValidationError(f"{recovery_label} has malformed sequence arrays")
        received_sequences = [_integer(value, f"{recovery_label} received sequence", 0xFFFF) for value in received]
        missing_sequences = [_integer(value, f"{recovery_label} missing sequence", 0xFFFF) for value in missing]
        if set(received_sequences) | set(missing_sequences) != set(sequences):
            raise VectorValidationError(f"{recovery_label} does not partition the FEC block")
        if set(received_sequences) & set(missing_sequences):
            raise VectorValidationError(f"{recovery_label} overlaps received and missing sequences")
        if len(missing_sequences) > 2:
            raise VectorValidationError(f"{recovery_label} requests unsupported recovery of more than two frames")
        received_by_sequence = {sequence: source_by_sequence[sequence] for sequence in received_sequences}
        recovered = recover_frames(
            [
                received_by_sequence[sequence].ljust(width, b"\0")
                if sequence in received_by_sequence
                else None
                for sequence in sequences
            ],
            parity[0],
            parity[1],
            lengths,
        )
        for sequence, actual in zip(sequences, recovered, strict=True):
            _compare(errors, f"{recovery_label} frame {sequence}", actual, source_by_sequence[sequence])
        _compare(
            errors,
            f"{recovery_label} output sequence order",
            [_integer(value, f"{recovery_label} output sequence", 0xFFFF) for value in expected_output],
            sequences,
        )
        expected_recovered = recovery_case.get("expectedRecovered", [])
        if not isinstance(expected_recovered, list):
            raise VectorValidationError(f"{recovery_label} expectedRecovered must be an array")
        expected_recovered_by_sequence: dict[int, bytes] = {}
        for expected_value in expected_recovered:
            if not isinstance(expected_value, dict):
                raise VectorValidationError(f"{recovery_label} expectedRecovered item must be an object")
            sequence = _integer(expected_value.get("audioSeq"), f"{recovery_label} expected audioSeq", 0xFFFF)
            expected_recovered_by_sequence[sequence] = _hex_bytes(expected_value.get("dataHex"), f"{recovery_label} expected dataHex")
        if fec_v2 and set(expected_recovered_by_sequence) != set(missing_sequences):
            raise VectorValidationError(f"{recovery_label} expectedRecovered does not match missing sequences")
        for sequence, expected in expected_recovered_by_sequence.items():
            _compare(errors, f"{recovery_label} recovered frame {sequence}", recovered[sequences.index(sequence)], expected)


def _load(root: Path, relative: str) -> dict[str, Any]:
    value = load_json(root / relative)
    if not isinstance(value, dict):
        raise VectorValidationError(f"{relative} must contain an object")
    return value


def _validate_fec_v1(root: Path) -> list[str]:
    document = _load(root, "test-vectors/fec-rs-6-2.json")
    if document.get("field") != "GF(256), primitive polynomial 0x11d":
        raise VectorValidationError("fec-rs-6-2 field declaration differs from GF(256)/0x11d")
    errors: list[str] = []
    _validate_block(errors, "FEC fixed-size v1", document, 4096, fec_v2=False)
    return errors


def _validate_fec_v2(root: Path) -> list[str]:
    document = _load(root, "test-vectors/fec-v2-variable-6-2.json")
    if document.get("field") != "GF(256), primitive polynomial 0x11d":
        raise VectorValidationError("fec-v2 field declaration differs from GF(256)/0x11d")
    max_frame_bytes = _integer(document.get("maxMediaFrameBytes"), "fec-v2 maxMediaFrameBytes", 0xFFFF)
    cases = document.get("cases")
    if not isinstance(cases, list):
        raise VectorValidationError("fec-v2 cases must be an array")
    errors: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"fec-v2 case {index} must be an object")
        name = case.get("name", f"case {index}")
        _validate_block(errors, f"FEC v2 {name}", case, max_frame_bytes, fec_v2=True)
    return errors


def validate_fec_vectors(root: Path) -> list[str]:
    """Recompute canonical FEC P/Q parity and recovery results independently."""
    errors: list[str] = []
    for label, validator in (("FEC fixed-size v1", _validate_fec_v1), ("FEC v2", _validate_fec_v2)):
        try:
            errors.extend(validator(root))
        except (VectorValidationError, ValueError, struct.error) as exc:
            errors.append(f"{label}: {exc}")
    return errors
