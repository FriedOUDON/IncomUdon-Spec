# Forward Error Correction

FEC is an optional media feature. The encoder forms blocks of six equal-size
codec frames and emits two parity packets after the sixth frame.

## FEC payload

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 2 | `block_start` (`u16`) |
| 2 | 1 | `block_size`; currently 6 |
| 3 | 1 | `parity_index`; 0 for P, 1 for Q |
| 4 | variable | parity data |

The FEC packet uses the same crypto mode as media and is forwarded only while
the sender holds the talk grant.

## Coding equations

For frame bytes `D[i]`, i = 0..5, over GF(256) with primitive polynomial
`0x11d`:

```text
P = D[0] XOR D[1] XOR D[2] XOR D[3] XOR D[4] XOR D[5]
Q = sum(GF_MUL(D[i], 2^i))
```

One missing frame can be recovered with P or Q. Two missing frames require
both P and Q. More than two missing frames are not recoverable. Variable-size
frames bypass FEC for their block so that received media is not delayed for
impossible parity recovery.

Receivers MUST key FEC state by sender ID and flush incomplete blocks when the
talker is released. See `../../test-vectors/fec-rs-6-2.json`.
