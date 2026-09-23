# Model assets

The repository contains several Ascend OM and ONNX model files. The active detector selects the first existing `best.om` from the candidate list in `src/ascend_main_other.py` and expects a 640 x 640 input. Other variants are not selected by the default service path.

| File | Format | Current repository evidence |
|---|---|---|
| `best.om` | Ascend OM | Default candidate used by the service when found in `src/`, the working directory, or the documented fallback paths. |
| `best1.om`, `best3.om`, `best4.om`, `model.om` | Ascend OM | Alternate artifacts; exact model version and measured behavior are not recorded here. |
| `best.onnx`, `oldbest.onnx` | ONNX | Source/export artifacts; exact relationship to each OM variant is not recorded here. |

Before replacing or deploying a model, record its source checkpoint, conversion command and CANN/ATC version, input/output tensor shapes, target SoC, and a board-side inference result. Keep the existing files until the replacement has been checked on the target board.
