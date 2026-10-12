# Jetlink vendored runtime

Source: https://github.com/zoompilot/jetlink
Revision: `b144d26721f116fe90341d64d0ee35ce30c39710` (0.7.2, tag `v0.7.2`).
The `jetlink/` package is copied without modifications. See LICENSE.
Carrot's adapter, device-role policy, process placement and deployment tools are
outside this directory. Updating the protocol requires testing both peers.

## Protocol 3

This copy speaks protocol 3 only. The comma's gadget and every server are
updated together, so a header from another version is a broken stream:
`jetlink/protocol.py` raises `ProtocolError` and the link is dropped.

Protocol 3 keeps the recurrent hidden state on the server:

- `INFER_REQ` carries the warped frame and the packed scalars with no
  `prev_feat` (`ModelSpec.packed_shapes` is desire/traffic_convention/action_t).
- `INFER_RESP` carries the model outputs less `hidden_state`, and
  `JetlinkClient.infer_end` rebuilds the full-length vector with that slice
  zeroed so `output_slices` stays valid. `SEND_RAW_PRED` sets `WANT_HIDDEN`,
  which asks the server for the whole vector on those frames.

Carrot code that needs the layout uses `ModelSpec.packed_layout`; the 0.3.0a1
`packed_sizes` helper is gone, and the reply is sized by `reply_nelem` while
`output_nelem` remains the full output.

## What this copy no longer provides

0.7.2 moves the server out of Python: it is the Swift `JetlinkKit` server
(the Mac, iPhone and Android apps, and `jetlink-server` on Linux). The
`jetlink/server/` package, `transport/usbbulk.py` and `onnx_patch.py` this
directory vendored at 0.3.0a1 have no replacement here. Carrot's host-side
tools under `tools/jetlink/` that imported them (the Python TensorRT server,
the Jetson/Mac provisioning pipeline, `bench.py`) do not run against this copy
and are kept only for reference until the host side is migrated to the Swift
server.
