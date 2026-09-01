# Directory UDP Protocol

The directory service is an optional UDP control-plane feature. It provisions
channel and speaker metadata and exposes a participant list without carrying
voice media.

## Security model

- Directory messages are authenticated with a configured pre-shared key (PSK).
- Receivers MUST reject messages from sources outside configured allowlists.
- Directory authentication does not replace channel audio encryption.
- Implementations MUST apply TTL values and discard stale directory state.

## Operations

- The Relay may push directory updates on a configured interval.
- Clients may pull a current participant list on demand.
- Clients cache the last successful directory response and may display it only
  with its capture time when a fresh pull fails.

The JSON schema and authenticated datagram framing will be added under
`schemas/` and `test-vectors/` after the Relay implementation is extracted.
