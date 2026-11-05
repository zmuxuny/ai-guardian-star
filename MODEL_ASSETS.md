# Model assets

The repository contains several Ascend OM and ONNX model files. The active detector selects the first existing `best.om` from the candidate list in `src/ascend_main_other.py` and expects a 640 x 640 input. Other variants are not selected by the default service path.

| File | Format | Current repository evidence |
|---|---|---|
| `best.om` | Ascend OM | Default candidate used by the service when found in `src/`, the working directory, or the documented fallback paths. |
| `best1.om`, `best3.om`, `best4.om`, `model.om` | Ascend OM | Alternate artifacts; exact model version and measured behavior are not recorded here. |
| `best.onnx`, `oldbest.onnx` | ONNX | Source/export artifacts; exact relationship to each OM variant is not recorded here. |

## Head-pose enrollment probe

The strict face-enrollment design evaluates the official 6DRepNet
`RepVGG-B1g2` model as a candidate for board-side yaw, pitch and roll
verification. The upstream implementation is MIT licensed:
`https://github.com/thohemp/6DRepNet`.

- Candidate input contract: one normalized RGB face crop, NCHW float32,
  `1x3x224x224`.
- Candidate output contract: continuous 6D rotation representation; the board
  probe orthogonalizes the two vectors into a rotation matrix before deriving
  yaw, pitch and roll.
- Repository policy: model weights, public benchmark images and user face
  samples are not committed. A deployed model ID must include the OM file
  SHA-256 and the output/preprocessing contract.
- Current status: only the fail-closed estimator/gate and privacy-bounded
  benchmark report are implemented. No ONNX/OM asset has been accepted or
  deployed yet. The target board was unreachable during the latest read-only
  environment query, so SoC, CANN/ATC version, conversion command, tensor I/O,
  accuracy and latency remain unverified.

Do not connect this candidate to the production enrollment endpoint until the
target board conversion and benchmark meet the thresholds recorded in the
approved face-enrollment design.

Before replacing or deploying a model, record its source checkpoint, conversion command and CANN/ATC version, input/output tensor shapes, target SoC, and a board-side inference result. Keep the existing files until the replacement has been checked on the target board.
