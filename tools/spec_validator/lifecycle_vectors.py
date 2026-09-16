"""Independent state-machine and lifecycle validation for specification vectors."""

from __future__ import annotations

import hashlib
import hmac
import json
import struct
from pathlib import Path
from typing import Any

from .loader import VectorValidationError, load_json


MEMBERSHIP_REFRESH_TYPES = {"KEEPALIVE", "CODEC_CONFIG", "PTT_ON", "PTT_REQUEST", "PTT_OFF"}
RELEASE_REASONS = {
    "CLIENT_PTT_OFF": 0,
    "SERVER_TALK_TIMEOUT": 1,
    "MEMBERSHIP_TIMEOUT": 2,
    "CLIENT_LEAVE": 3,
    "SERVER_POLICY": 4,
    "IDENTITY_EXPIRED": 5,
    "SERVICE_ADMISSION_REVOKED": 6,
    "PREEMPTED": 7,
    "SERVICE_ADMISSION_EXPIRED": 8,
}
MAX_DIRECTORY_REPLAY_SEQUENCE = (1 << 53) - 1
MEDIA_SECURITY_MODES = frozenset({"no-crypto", "legacy-xor", "aes-gcm-v2"})


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


def _load(root: Path, relative: str) -> dict[str, Any]:
    value = load_json(root / relative)
    if not isinstance(value, dict):
        raise VectorValidationError(f"{relative} must contain an object")
    return value


def _compare(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual == expected:
        return
    if isinstance(actual, bytes) and isinstance(expected, bytes):
        errors.append(f"{label}: expected {expected.hex()}, got {actual.hex()}")
    else:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def _talk_release_payload(talker_id: int, reason: str) -> bytes:
    if reason not in RELEASE_REASONS:
        raise VectorValidationError(f"unknown TALK_RELEASE reason: {reason!r}")
    if talker_id == 0:
        raise VectorValidationError("TALK_RELEASE talker_id must be non-zero")
    return struct.pack(">IB", talker_id, RELEASE_REASONS[reason])


def _validate_ptt_timeout(root: Path) -> list[str]:
    document = _load(root, "test-vectors/ptt-timeout-v1.json")
    errors: list[str] = []
    releases = document.get("talk_release_payloads")
    timelines = document.get("timeline_cases")
    if not isinstance(releases, list) or not isinstance(timelines, list):
        raise VectorValidationError("PTT timeout vectors must contain arrays")
    for index, release in enumerate(releases):
        if not isinstance(release, dict):
            raise VectorValidationError(f"TALK_RELEASE fixture {index} must be an object")
        reason = release.get("reason")
        if reason not in RELEASE_REASONS:
            raise VectorValidationError(f"TALK_RELEASE fixture {index} has unknown reason")
        _compare(errors, f"TALK_RELEASE {reason} reason byte", RELEASE_REASONS[reason], release.get("reason_byte"))
        payload = _talk_release_payload(
            _integer(release.get("talker_id"), f"TALK_RELEASE {reason} talker_id", 0xFFFFFFFF),
            reason,
        )
        _compare(errors, f"TALK_RELEASE {reason} payload", payload, _hex_bytes(release.get("payload_hex"), f"TALK_RELEASE {reason} payload"))
    for index, timeline in enumerate(timelines):
        if not isinstance(timeline, dict):
            raise VectorValidationError(f"PTT timeout timeline {index} must be an object")
        name = timeline.get("name", f"timeline {index}")
        maximum = _integer(timeline.get("maximum_talk_seconds"), f"{name} maximum_talk_seconds", 0xFFFF)
        grant_time = _integer(timeline.get("grant_time_ms"), f"{name} grant_time_ms", (1 << 63) - 1)
        expected_deadline = timeline.get("deadline_ms")
        if maximum == 0:
            _compare(errors, f"{name} disabled deadline", expected_deadline, None)
            _compare(errors, f"{name} ordinary release", timeline.get("release_reason"), "CLIENT_PTT_OFF")
            continue
        deadline = grant_time + maximum * 1000
        _compare(errors, f"{name} deadline", deadline, expected_deadline)
        duplicate = timeline.get("duplicate_ptt_on_ms")
        if duplicate is not None:
            duplicate_time = _integer(duplicate, f"{name} duplicate_ptt_on_ms", (1 << 63) - 1)
            if not grant_time <= duplicate_time < deadline:
                errors.append(f"{name}: duplicate PTT_ON must occur during the original lease")
            _compare(errors, f"{name} duplicate PTT_ON does not extend deadline", deadline, expected_deadline)
        _compare(errors, f"{name} release reason", timeline.get("release_reason"), "SERVER_TALK_TIMEOUT")
        _compare(errors, f"{name} forwards before deadline", timeline.get("must_forward_before_deadline"), True)
        _compare(errors, f"{name} rejects at deadline", timeline.get("must_reject_at_or_after_deadline"), True)
    return errors


def _valid_membership_pair(lease: int, keepalive: int) -> bool:
    return 15 <= lease <= 300 and 1 <= keepalive <= lease // 3


def _control_packet_accepted(control: dict[str, Any], packet: dict[str, Any]) -> bool:
    mode = control.get("mode")
    configured = control.get("channelHasConfiguredControlKey")
    valid = packet.get("valid", True)
    authenticated = packet.get("authenticated", False)
    if not isinstance(valid, bool) or not isinstance(authenticated, bool) or not isinstance(configured, bool):
        raise VectorValidationError("control acceptance fixture contains non-boolean fields")
    if mode not in {"required", "optional", "off"}:
        raise VectorValidationError(f"unknown Control Authentication mode: {mode!r}")
    authentication_required = mode == "required" or (mode == "optional" and configured)
    return valid and (authenticated or not authentication_required)


def _validate_media_security_mode_registry(root: Path) -> list[str]:
    document = _load(root, "test-vectors/packet-envelope-v1.json")
    cases = document.get("codecConfigPolicyCases")
    if not isinstance(cases, list):
        raise VectorValidationError("codecConfigPolicyCases must be an array")

    errors: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"codec configuration policy case {index} must be an object")
        name = case.get("name", f"codec configuration policy case {index}")
        mode = case.get("mediaSecurityMode")
        expected = case.get("expected")
        if not isinstance(name, str) or not isinstance(mode, str) or not isinstance(expected, str):
            raise VectorValidationError(f"codec configuration policy case {index} has invalid metadata")
        if mode not in MEDIA_SECURITY_MODES:
            _compare(
                errors,
                f"{name} rejected unknown media security mode",
                "reject_unknown_media_security_mode",
                expected,
            )
        elif expected == "reject_unknown_media_security_mode":
            errors.append(f"{name}: registered media security mode {mode!r} is marked unknown")
    return errors


def _validate_membership(root: Path) -> list[str]:
    document = _load(root, "test-vectors/membership-lease-v1.json")
    errors: list[str] = []
    server_config = document.get("serverConfig")
    if not isinstance(server_config, dict):
        raise VectorValidationError("membership serverConfig must be an object")
    lease = _integer(server_config.get("membershipLeaseSeconds"), "serverConfig membershipLeaseSeconds", 0xFFFF)
    keepalive = _integer(server_config.get("keepaliveIntervalSeconds"), "serverConfig keepaliveIntervalSeconds", 0xFFFF)
    if not _valid_membership_pair(lease, keepalive):
        errors.append("membership serverConfig has an invalid lease/keepalive pair")
    multi_talk = server_config.get("multiTalkEnabled")
    if not isinstance(multi_talk, bool):
        raise VectorValidationError("serverConfig multiTalkEnabled must be boolean")
    server_payload = struct.pack(
        ">HBBHH",
        _integer(server_config.get("maximumTalkSeconds"), "serverConfig maximumTalkSeconds", 0xFFFF),
        int(multi_talk),
        _integer(server_config.get("maximumActiveTalkers"), "serverConfig maximumActiveTalkers", 0xFF),
        lease,
        keepalive,
    )
    _compare(errors, "membership SERVER_CONFIG payload", server_payload, _hex_bytes(server_config.get("payloadHex"), "serverConfig payloadHex"))
    bootstrap = document.get("bootstrap")
    if not isinstance(bootstrap, dict):
        raise VectorValidationError("membership bootstrap must be an object")
    _compare(errors, "membership bootstrap keepalive", bootstrap.get("keepaliveIntervalSeconds"), 5)
    _compare(errors, "membership bootstrap lifetime", bootstrap.get("appliesUntil"), "valid_SERVER_CONFIG_received")

    cases = document.get("cases")
    if not isinstance(cases, list):
        raise VectorValidationError("membership cases must be an array")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"membership case {index} must be an object")
        name = case.get("name", f"membership case {index}")
        if "refreshPackets" in case:
            case_lease = _integer(case.get("leaseSeconds"), f"{name} leaseSeconds", 0xFFFF)
            deadline = _integer(case.get("joinAcceptedAtSeconds"), f"{name} joinAcceptedAtSeconds", (1 << 63) - 1) + case_lease
            packets = case.get("refreshPackets")
            if not isinstance(packets, list):
                raise VectorValidationError(f"{name} refreshPackets must be an array")
            for packet in packets:
                if not isinstance(packet, dict) or packet.get("type") not in MEMBERSHIP_REFRESH_TYPES | {"AUDIO", "FEC"}:
                    raise VectorValidationError(f"{name} has an ineligible refresh packet")
                received = _integer(packet.get("receivedAtSeconds"), f"{name} refresh receive time", (1 << 63) - 1)
                if received >= deadline:
                    errors.append(f"{name}: refresh packet arrives after the existing membership deadline")
                deadline = received + case_lease
                _compare(errors, f"{name} refresh deadline", deadline, packet.get("expectedDeadlineSeconds"))
            member_at = _integer(case.get("expectedMembershipAtSeconds"), f"{name} expectedMembershipAtSeconds", (1 << 63) - 1)
            if member_at >= deadline:
                errors.append(f"{name}: membership is expected after its deadline")
        elif "nonRefreshPackets" in case:
            case_lease = _integer(case.get("leaseSeconds"), f"{name} leaseSeconds", 0xFFFF)
            deadline = _integer(case.get("joinAcceptedAtSeconds"), f"{name} joinAcceptedAtSeconds", (1 << 63) - 1) + case_lease
            packets = case.get("nonRefreshPackets")
            if not isinstance(packets, list) or any(packet.get("type") not in {"PING", "PONG"} for packet in packets if isinstance(packet, dict)):
                raise VectorValidationError(f"{name} nonRefreshPackets must contain only PING/PONG")
            _compare(errors, f"{name} expiry", deadline, case.get("expectedExpiryAtSeconds"))
            _compare(errors, f"{name} active talk release", case.get("expectedActiveTalkReleaseReason"), "MEMBERSHIP_TIMEOUT")
        elif "membershipLeaseSeconds" in case:
            valid = _valid_membership_pair(
                _integer(case.get("membershipLeaseSeconds"), f"{name} lease", 0xFFFF),
                _integer(case.get("keepaliveIntervalSeconds"), f"{name} keepalive", 0xFFFF),
            )
            _compare(errors, f"{name} acceptance", valid, case.get("expectedServerConfigAcceptance"))
        elif "joinSnapshot" in case:
            snapshot = case.get("joinSnapshot")
            reloaded = case.get("reloadedPolicy")
            if not isinstance(snapshot, dict) or not isinstance(reloaded, dict):
                raise VectorValidationError(f"{name} policy snapshots must be objects")
            _compare(errors, f"{name} existing membership", snapshot, case.get("expectedExistingMembership"))
            _compare(errors, f"{name} new membership", reloaded, case.get("expectedNewMembership"))
        else:
            raise VectorValidationError(f"{name} is not a recognized membership lifecycle case")

    control_cases = document.get("controlAuthenticationRefreshCases")
    if not isinstance(control_cases, list):
        raise VectorValidationError("controlAuthenticationRefreshCases must be an array")
    for index, case in enumerate(control_cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"control refresh case {index} must be an object")
        name = case.get("name", f"control refresh case {index}")
        control = case.get("controlAuthentication")
        packet = case.get("packet")
        if not isinstance(control, dict) or not isinstance(packet, dict):
            raise VectorValidationError(f"{name} must contain controlAuthentication and packet objects")
        accepted = _control_packet_accepted(control, packet)
        refresh = accepted and packet.get("type") in MEMBERSHIP_REFRESH_TYPES
        lease_seconds = _integer(case.get("leaseSeconds"), f"{name} leaseSeconds", 0xFFFF)
        join_time = _integer(case.get("joinAcceptedAtSeconds"), f"{name} joinAcceptedAtSeconds", (1 << 63) - 1)
        received = _integer(packet.get("receivedAtSeconds"), f"{name} receivedAtSeconds", (1 << 63) - 1)
        if received >= join_time + lease_seconds:
            errors.append(f"{name}: control packet arrives after membership expiry")
        _compare(errors, f"{name} packet acceptance", accepted, case.get("expectedPacketAcceptance"))
        _compare(errors, f"{name} membership refresh", refresh, case.get("expectedMembershipRefresh"))
        _compare(errors, f"{name} deadline", received + lease_seconds if refresh else join_time + lease_seconds, case.get("expectedDeadlineSeconds"))
    return errors


def _validate_admission_expiry(root: Path) -> list[str]:
    errors: list[str] = []
    identity = _load(root, "test-vectors/identity-admission-v1.json")
    cases = identity.get("membership_expiry_cases")
    if not isinstance(cases, list):
        raise VectorValidationError("identity membership_expiry_cases must be an array")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"identity expiry case {index} must be an object")
        name = case.get("name", f"identity expiry case {index}")
        normal = _integer(case.get("normal_membership_deadline"), f"{name} normal deadline", (1 << 63) - 1)
        ticket = _integer(case.get("ticket_exp"), f"{name} ticket expiry", (1 << 63) - 1)
        _compare(errors, f"{name} effective expiry", min(normal, ticket), case.get("effective_membership_expiry"))
        reason = "MEMBERSHIP_TIMEOUT" if normal <= ticket else "IDENTITY_EXPIRED"
        _compare(errors, f"{name} release reason", reason, case.get("release_reason"))
        _compare(errors, f"{name} release reason byte", RELEASE_REASONS[reason], case.get("release_reason_byte"))
        payload = _talk_release_payload(_integer(case.get("talker_id"), f"{name} talker_id", 0xFFFFFFFF), reason)
        _compare(errors, f"{name} TALK_RELEASE payload", payload, _hex_bytes(case.get("talk_release_payload_hex"), f"{name} payload"))

    service = _load(root, "test-vectors/management/service-admission-v1.json")
    service_cases = service.get("expiry_cases")
    if not isinstance(service_cases, list):
        raise VectorValidationError("service expiry_cases must be an array")
    for index, case in enumerate(service_cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"service expiry case {index} must be an object")
        name = case.get("name", f"service expiry case {index}")
        permission = _integer(case.get("grant_perm"), f"{name} grant_perm", 0xFF)
        grant_exp = _integer(case.get("grant_exp"), f"{name} grant_exp", (1 << 63) - 1)
        grace = _integer(case.get("grace_seconds"), f"{name} grace_seconds", 0xFFFFFFFF)
        normal = _integer(case.get("normal_membership_deadline"), f"{name} normal deadline", (1 << 63) - 1)
        talk_capable = bool(permission & 0x02)
        service_deadline = grant_exp if talk_capable else grant_exp + grace
        _compare(errors, f"{name} effective expiry", min(normal, service_deadline), case.get("effective_membership_expiry"))
        if case.get("active_talk"):
            reason = "MEMBERSHIP_TIMEOUT" if normal <= service_deadline else "SERVICE_ADMISSION_EXPIRED"
            _compare(errors, f"{name} release reason", reason, case.get("release_reason"))
            _compare(errors, f"{name} release reason byte", RELEASE_REASONS[reason], case.get("release_reason_byte"))
            payload = _talk_release_payload(_integer(case.get("talker_id"), f"{name} talker_id", 0xFFFFFFFF), reason)
            _compare(errors, f"{name} TALK_RELEASE payload", payload, _hex_bytes(case.get("talk_release_payload_hex"), f"{name} payload"))
    return errors


def _validate_directory_lifecycle(root: Path) -> list[str]:
    document = _load(root, "test-vectors/directory-v3.json")
    limits = document.get("limits")
    if not isinstance(limits, dict):
        raise VectorValidationError("Directory limits must be an object")
    errors: list[str] = []
    replay_window = _integer(limits.get("replayWindowSize"), "Directory replayWindowSize", 0xFFFF)
    max_registrations = _integer(limits.get("maxActiveRegistrations"), "Directory maxActiveRegistrations", 0xFFFF)
    ttl_seconds = _integer(limits.get("registrationTtlSeconds"), "Directory registrationTtlSeconds", 0xFFFF)
    _compare(errors, "Directory replay window size", replay_window, 64)
    _compare(errors, "Directory max registrations", max_registrations, 64)
    _compare(errors, "Directory registration TTL", ttl_seconds, 90)

    replay_cases = document.get("replayWindowCases")
    if not isinstance(replay_cases, list):
        raise VectorValidationError("Directory replayWindowCases must be an array")
    for index, case in enumerate(replay_cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"Directory replay case {index} must be an object")
        high = case.get("acceptedHighWatermark")
        candidate = _integer(case.get("candidateSequence"), f"Directory replay case {index} candidate", MAX_DIRECTORY_REPLAY_SEQUENCE)
        seen = {_integer(value, f"Directory replay case {index} seen", MAX_DIRECTORY_REPLAY_SEQUENCE) for value in case.get("acceptedSequences", [])}
        if candidate in seen:
            expected = "reject_duplicate_sequence"
        elif high is not None and candidate < _integer(high, f"Directory replay case {index} high", MAX_DIRECTORY_REPLAY_SEQUENCE) - (replay_window - 1):
            expected = "reject_stale_sequence"
        else:
            expected = "accept_unseen_sequence"
        _compare(errors, f"Directory replay case {index}", expected, case.get("expected"))

    fragments = document.get("fragmentReassemblyCases")
    if not isinstance(fragments, list):
        raise VectorValidationError("Directory fragmentReassemblyCases must be an array")
    media_fragments = document.get("crypto", {}).get("mediaPortParticipantsFragments", [])
    sequence_to_fragment: dict[int, tuple[int, int]] = {}
    if isinstance(media_fragments, list):
        for fixture in media_fragments:
            if not isinstance(fixture, dict):
                continue
            payload = json.loads(fixture["plaintextUtf8"])
            sequence_to_fragment[fixture["sequence"]] = (
                payload["fragment"]["index"],
                payload["participants"][0]["senderId"],
            )
    for case in fragments:
        if not isinstance(case, dict):
            raise VectorValidationError("Directory fragment reassembly case must be an object")
        name = case.get("name", "fragment case")
        if "fragment" in case:
            fragment = case["fragment"]
            complete = isinstance(fragment, dict) and set(case.get("receivedIndexes", [])) == set(range(fragment.get("count", 0)))
            _compare(errors, f"{name} completion", "apply_atomically" if complete else "discard_incomplete_keep_previous_state", case.get("expected"))
        elif "receivedSequenceOrder" in case:
            indexes = [sequence_to_fragment.get(sequence, (-1, -1))[0] for sequence in case["receivedSequenceOrder"]]
            sender_ids = [sequence_to_fragment[sequence][1] for sequence in sorted(case["receivedSequenceOrder"])]
            complete = set(indexes) == set(range(case.get("fragmentCount", 0)))
            _compare(errors, f"{name} completion", complete, True)
            _compare(errors, f"{name} sender IDs", sender_ids, case.get("expectedParticipantSenderIds"))
            _compare(errors, f"{name} expected action", case.get("expected"), "reassemble_and_apply_atomically")
        elif "conflictingIndex" in case:
            _compare(errors, f"{name} expected action", case.get("expected"), "discard_set_increment_reassembly_conflicts")
        elif "fragmentSets" in case:
            complete = any(set(item.get("receivedIndexes", [])) == {0, 1, 2} for item in case["fragmentSets"])
            _compare(errors, f"{name} completion", complete, False)
            _compare(errors, f"{name} expected action", case.get("expected"), "no_complete_response_applied")
        else:
            indexes = case.get("receivedIndexes", [])
            complete = set(indexes) == set(range(case.get("fragmentCount", 0)))
            action = "ignore_duplicate_reassemble_and_apply_atomically" if complete else "discard_incomplete_keep_previous_state"
            _compare(errors, f"{name} expected action", case.get("expected"), action)

    pages = document.get("snapshotPaginationCases")
    if not isinstance(pages, list):
        raise VectorValidationError("Directory snapshotPaginationCases must be an array")
    for case in pages:
        if not isinstance(case, dict):
            raise VectorValidationError("Directory pagination case must be an object")
        name = case.get("name", "pagination case")
        if "pages" in case:
            page_values = case["pages"]
            complete = isinstance(page_values, list) and all(page.get("complete") for page in page_values) and [page.get("index") for page in page_values] == list(range(len(page_values))) and page_values[-1].get("nextCursor") is None
            _compare(errors, f"{name} action", "replace_static_snapshot_atomically" if complete else "retain_previous_snapshot", case.get("expected"))
        elif "receivedRevisions" in case:
            revisions = case["receivedRevisions"]
            _compare(errors, f"{name} action", "discard_staged_snapshot_restart_pagination" if len(set(revisions)) > 1 else "replace_static_snapshot_atomically", case.get("expected"))
        else:
            _compare(errors, f"{name} action", "retain_previous_snapshot", case.get("expected"))

    registration = document.get("registrationLifecycleCases")
    if not isinstance(registration, dict):
        raise VectorValidationError("Directory registrationLifecycleCases must be an object")
    registration_cases = registration.get("cases")
    if not isinstance(registration_cases, list):
        raise VectorValidationError("Directory registration lifecycle cases must be an array")
    _compare(errors, "Directory registration key", registration.get("registrationKey"), ["channelId", "instanceId"])
    _compare(errors, "Directory registration capacity scope", registration.get("capacityScope"), "relay-wide")
    _compare(errors, "Directory heartbeat failure response", registration.get("registerHeartbeatFailureResponse"), "silent_drop_no_error")
    schedule = registration.get("clientRenewalSchedule")
    if not isinstance(schedule, dict):
        raise VectorValidationError("Directory clientRenewalSchedule must be an object")
    _compare(errors, "Directory register on startup/endpoint change", schedule.get("registerOnStartupAndEndpointChange"), True)
    _compare(errors, "Directory maximum heartbeat interval", schedule.get("maximumHeartbeatIntervalSeconds"), 30)
    _compare(errors, "Directory maximum re-registration interval", schedule.get("maximumReregistrationIntervalSeconds"), 60)
    ttl_ms = ttl_seconds * 1000
    for case in registration_cases:
        if not isinstance(case, dict):
            raise VectorValidationError("Directory registration case must be an object")
        name = case.get("name", "registration case")
        initial = case.get("initial")
        input_value = case.get("input")
        expected = case.get("expected")
        if name == "periodic_reregister_recovers_lost_relay_state":
            inputs = case.get("inputs")
            if not isinstance(inputs, list) or [item.get("expected") for item in inputs] != ["silent_drop_unknown_instance", "create_registration"]:
                errors.append(f"{name}: recovery sequence is invalid")
            register_time = inputs[1].get("atSeconds") if isinstance(inputs, list) and len(inputs) == 2 and isinstance(inputs[1], dict) else None
            _compare(errors, f"{name} expiry", expected.get("registrationExpiresAtSecondsAfterInitialStateLoss") if isinstance(expected, dict) else None, register_time + ttl_seconds if isinstance(register_time, int) else None)
            continue
        if name == "new_register_at_capacity_is_silently_dropped_without_eviction":
            if not isinstance(expected, dict):
                raise VectorValidationError(f"{name} expected must be an object")
            _compare(errors, f"{name} state", expected.get("state"), "unregistered")
            _compare(errors, f"{name} slots", expected.get("activeRegistrations"), max_registrations)
            _compare(errors, f"{name} eviction", expected.get("evictedRegistrations"), 0)
            continue
        if name == "expiry_removes_record_and_stops_periodic_publication":
            if not isinstance(initial, dict) or not isinstance(input_value, dict) or not isinstance(expected, dict):
                raise VectorValidationError(f"{name} is malformed")
            expired = input_value.get("relayMonotonicMs") >= initial.get("registrationExpiresAtRelayMonotonicMs")
            _compare(errors, f"{name} expiry", expired, True)
            _compare(errors, f"{name} state", expected.get("state"), "unregistered")
            _compare(errors, f"{name} publications", expected.get("pendingUnsolicitedPublications"), 0)
            continue
        if not isinstance(input_value, dict):
            raise VectorValidationError(f"{name} input must be an object")
        packet_type = input_value.get("type", "register")
        if packet_type == "heartbeat":
            if initial is None:
                _compare(errors, f"{name} action", expected, "silent_drop_no_registration_created_no_error")
            elif not isinstance(initial, dict):
                raise VectorValidationError(f"{name} initial must be an object")
            elif input_value.get("acceptedAtRelayMonotonicMs", 0) >= initial.get("registrationExpiresAtRelayMonotonicMs", 0):
                _compare(errors, f"{name} action", expected, "silent_drop_expired_no_registration_created_no_error")
            elif input_value.get("sourceEndpoint") != initial.get("sourceEndpoint"):
                if not isinstance(expected, dict):
                    raise VectorValidationError(f"{name} expected must be an object")
                _compare(errors, f"{name} state", expected.get("state"), "unchanged")
                _compare(errors, f"{name} endpoint", expected.get("sourceEndpoint"), initial.get("sourceEndpoint"))
                _compare(errors, f"{name} expiry", expected.get("registrationExpiresAtRelayMonotonicMs"), initial.get("registrationExpiresAtRelayMonotonicMs"))
            else:
                if not isinstance(expected, dict):
                    raise VectorValidationError(f"{name} expected must be an object")
                _compare(errors, f"{name} state", expected.get("state"), "registered")
                _compare(errors, f"{name} expiry", expected.get("registrationExpiresAtRelayMonotonicMs"), input_value.get("acceptedAtRelayMonotonicMs") + ttl_ms)
        elif packet_type == "register":
            if isinstance(initial, dict):
                if not isinstance(expected, dict):
                    raise VectorValidationError(f"{name} expected must be an object")
                _compare(errors, f"{name} state", expected.get("state"), "replaced")
                _compare(errors, f"{name} endpoint", expected.get("sourceEndpoint"), input_value.get("sourceEndpoint"))
                _compare(errors, f"{name} expiry", expected.get("registrationExpiresAtRelayMonotonicMs"), input_value.get("acceptedAtRelayMonotonicMs") + ttl_ms)
                if "activeRegistrations" in expected:
                    _compare(errors, f"{name} active registration count", expected.get("activeRegistrations"), initial.get("activeRegistrations"))
            else:
                if not isinstance(expected, dict):
                    raise VectorValidationError(f"{name} expected must be an object")
                _compare(errors, f"{name} state", expected.get("state"), "registered")
                _compare(errors, f"{name} expiry", expected.get("registrationExpiresAtRelayMonotonicMs"), input_value.get("acceptedAtRelayMonotonicMs") + ttl_ms)
                if "activeRegistrations" in expected:
                    _compare(errors, f"{name} active registration count", expected.get("activeRegistrations"), 1)
        else:
            raise VectorValidationError(f"{name} has unsupported registration packet type {packet_type!r}")
    return errors


def _validate_media_replay(root: Path) -> list[str]:
    document = _load(root, "test-vectors/media-replay-v1.json")
    errors: list[str] = []
    window = _integer(document.get("windowSize"), "media replay windowSize", 0xFFFF)
    _compare(errors, "media replay window size", window, 64)
    cases = document.get("cases")
    if not isinstance(cases, list):
        raise VectorValidationError("media replay cases must be an array")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise VectorValidationError(f"media replay case {index} must be an object")
        name = case.get("name", f"media replay case {index}")
        if "announcedMediaNonceBase96Hex" in case:
            expected = "accept_and_mark_seen" if case.get("announcedMediaNonceBase96Hex") == case.get("packetMediaNonceBase96Hex") else "reject_unannounced_session"
            _compare(errors, f"{name} action", expected, case.get("expected"))
            continue
        high = case.get("initialHighestAuthenticatedCounter")
        highest = None if high is None else _integer(high, f"{name} high counter", 0xFFFFFFFF)
        seen = {_integer(value, f"{name} seen counter", 0xFFFFFFFF) for value in case.get("initialSeenCounters", [])}
        counter = _integer(case.get("counter"), f"{name} counter", 0xFFFFFFFF)
        authentication = case.get("authentication")
        if highest is not None and counter < highest - (window - 1):
            expected = "reject_stale"
        elif authentication != "valid":
            expected = "reject_authentication_failure_without_state_change"
        elif counter in seen:
            expected = "reject_replay"
        else:
            expected = "accept_and_mark_seen"
            highest = counter if highest is None else max(highest, counter)
            seen.add(counter)
            seen = {value for value in seen if value >= highest - (window - 1)}
        _compare(errors, f"{name} action", expected, case.get("expected"))
        _compare(errors, f"{name} high counter", highest, case.get("resultHighestAuthenticatedCounter"))
        _compare(errors, f"{name} seen counters", sorted(seen, reverse=True), case.get("resultSeenCounters"))
    return errors


def _validate_floor_interrupt(root: Path) -> list[str]:
    document = _load(root, "test-vectors/floor-interrupt-v1.json")
    errors: list[str] = []
    control = document.get("control_auth")
    packets = document.get("packets")
    if not isinstance(control, dict) or not isinstance(packets, list):
        raise VectorValidationError("Floor Interrupt control_auth and packets are required")
    key = _hex_bytes(control.get("control_key_hex"), "Floor Interrupt control key")
    domain = _hex_bytes(control.get("domain_hex"), "Floor Interrupt control domain")
    packet_types = {"PTT_REQUEST": 0x1A, "TALK_RELEASE": 0x08}
    for fixture in packets:
        if not isinstance(fixture, dict):
            raise VectorValidationError("Floor Interrupt packet fixture must be an object")
        name = fixture.get("name", "Floor Interrupt packet")
        fields = fixture.get("fields")
        auth = fixture.get("controlAuth")
        if not isinstance(fields, dict) or not isinstance(auth, dict):
            raise VectorValidationError(f"{name} is malformed")
        packet_type = fields.get("type")
        header = struct.pack(
            ">BBHIIHH",
            _integer(fields.get("version"), f"{name} version", 0xFF),
            packet_types[packet_type],
            _integer(fields.get("headerLen"), f"{name} headerLen", 0xFFFF),
            _integer(fields.get("channelId"), f"{name} channelId", 0xFFFFFFFF),
            _integer(fields.get("senderId"), f"{name} senderId", 0xFFFFFFFF),
            _integer(fields.get("seq"), f"{name} seq", 0xFFFF),
            _integer(fields.get("flags"), f"{name} flags", 0xFFFF),
        ) + _hex_bytes(auth.get("nonceHex"), f"{name} nonce") + struct.pack(">I", _integer(auth.get("controlKeyId"), f"{name} control key ID", 0xFFFFFFFF))
        _compare(errors, f"{name} authenticated header", header, _hex_bytes(auth.get("authenticatedHeaderHex"), f"{name} authenticatedHeaderHex"))
        payload = _hex_bytes(fixture.get("payloadHex"), f"{name} payloadHex")
        tag = hmac.new(key, domain + header + payload, hashlib.sha256).digest()[:16]
        _compare(errors, f"{name} HMAC tag", tag, _hex_bytes(auth.get("tagHex"), f"{name} tagHex"))
        _compare(errors, f"{name} datagram", header + payload + tag, _hex_bytes(fixture.get("datagramHex"), f"{name} datagramHex"))

    authorization = document.get("authorization_cases")
    if not isinstance(authorization, list):
        raise VectorValidationError("Floor Interrupt authorization_cases must be an array")
    for case in authorization:
        if not isinstance(case, dict):
            raise VectorValidationError("Floor Interrupt authorization case must be an object")
        name = case.get("name", "Floor Interrupt authorization case")
        permitted = (
            case.get("identity_admission_mode") == "required"
            and case.get("control_auth_required") is True
            and (_integer(case.get("requester_perm"), f"{name} permission", 0xFF) & 0x06) == 0x06
            and _integer(case.get("requester_priority"), f"{name} priority", 0xFF) > 0
        )
        active = case.get("active_talkers")
        if not isinstance(active, list) or not active:
            raise VectorValidationError(f"{name} must have active talkers")
        victim = min(
            active,
            key=lambda talker: (
                _integer(talker.get("priority"), f"{name} active priority", 0xFF),
                _integer(talker.get("sender_id"), f"{name} active sender", 0xFFFFFFFF),
            ),
        )
        victim_priority = _integer(victim.get("priority"), f"{name} victim priority", 0xFF)
        requester_priority = _integer(case.get("requester_priority"), f"{name} priority", 0xFF)
        actual = f"preempt_sender_{victim['sender_id']}" if permitted and requester_priority > victim_priority else "deny"
        _compare(errors, f"{name} result", actual, case.get("result"))
    receiver_cases = document.get("receiver_release_cases")
    if not isinstance(receiver_cases, list):
        raise VectorValidationError("Floor Interrupt receiver_release_cases must be an array")
    for case in receiver_cases:
        if not isinstance(case, dict) or not isinstance(case.get("expected"), dict):
            raise VectorValidationError("Floor Interrupt receiver release case is malformed")
        name = case.get("name", "Floor Interrupt receiver release")
        expected = case["expected"]
        _compare(errors, f"{name} reason", case.get("release_reason"), "PREEMPTED")
        _compare(errors, f"{name} drain", expected.get("drain_queued_media"), False)
        _compare(errors, f"{name} discard media", expected.get("discard_unrendered_media"), True)
        _compare(errors, f"{name} discard FEC", expected.get("discard_pending_fec_blocks"), True)
        _compare(errors, f"{name} discard recovered", expected.get("discard_recovered_not_rendered_media"), True)
        _compare(errors, f"{name} suppress cue", expected.get("suppress_end_of_talk_cue"), True)
        _compare(errors, f"{name} replacement delay", expected.get("delay_replacement_talker"), False)
        fade = _integer(expected.get("fade_out_max_ms"), f"{name} fade_out_max_ms", 0xFFFF)
        if fade > 20:
            errors.append(f"{name}: PREEMPTED fade exceeds 20 ms")
    return errors


def validate_lifecycle_vectors(root: Path) -> list[str]:
    """Validate deterministic policy, expiry, replay, and state-transition cases."""
    validators = (
        ("PTT timeout", _validate_ptt_timeout),
        ("Membership lease", _validate_membership),
        ("Media security mode registry", _validate_media_security_mode_registry),
        ("Admission expiry", _validate_admission_expiry),
        ("Directory lifecycle", _validate_directory_lifecycle),
        ("Media replay", _validate_media_replay),
        ("Floor Interrupt", _validate_floor_interrupt),
    )
    errors: list[str] = []
    for label, validator in validators:
        try:
            errors.extend(validator(root))
        except (KeyError, TypeError, ValueError, VectorValidationError, struct.error) as exc:
            errors.append(f"{label}: {exc}")
    return errors
