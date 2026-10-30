"""Policy-only legal argmax adapters for selected Torch and actual ONNX files."""

import sys

from training.supervision import ACTIONS


class TorchStudent:
    def __init__(self, model, *, device):
        if sys.platform != "linux" or device not in ("cpu", "cuda"):
            raise ValueError("student inference requires external Linux CPU/CUDA")
        if getattr(model, "backend", None) == "ort-cpu" and device != "cpu":
            raise ValueError("ORT CPU reference cannot be labelled CUDA")
        self.model, self.device = model.to(device).eval(), device

    def _outputs(self, game):
        import torch

        legal = sorted(game.legal_actions())
        if not legal or any(
            type(action) is not int or not 0 <= action < ACTIONS for action in legal
        ):
            raise ValueError("student requires nonempty canonical legal actions")
        features = torch.from_numpy(game.features()).unsqueeze(0).to(self.device)
        if (
            features.shape != (1, 729, 43)
            or features.dtype != torch.float32
            or not torch.isfinite(features).all()
        ):
            raise ValueError("student feature shape/dtype/finite differs")
        with torch.inference_mode():
            policy, value = self.model(features)
            if (
                policy.shape != (1, ACTIONS)
                or value.shape != (1, 1)
                or policy.dtype != torch.float32
                or value.dtype != torch.float32
                or not torch.isfinite(policy).all()
                or not torch.isfinite(value).all()
            ):
                raise ValueError("student output shape/dtype/finite differs")
            return legal, policy, value

    def __call__(self, game):
        import torch

        legal, policy, _value = self._outputs(game)
        with torch.inference_mode():
            # Sorted canonical IDs make argmax's first occurrence the fixed tie rule.
            return legal[policy[0, legal].argmax().item()]


def make_ort_model(path, *, precision, session=None):
    if sys.platform != "linux" or precision not in ("fp32", "fp16", "int8"):
        raise ValueError("ONNX evaluation requires external Linux and a known format")
    import torch
    from torch import nn

    if session is None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            if precision == "int8"
            else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        session = ort.InferenceSession(
            path, options, providers=["CPUExecutionProvider"]
        )

    class OrtModel(nn.Module):
        backend = "ort-cpu"

        def forward(self, features):
            if features.shape != (1, 729, 43) or features.dtype != torch.float32:
                raise ValueError("exported ONNX requires fixed batch1 FP32 features")
            policy, value = session.run(
                ["policy", "value"], {"features": features.detach().cpu().numpy()}
            )
            return torch.from_numpy(policy), torch.from_numpy(value)

    return OrtModel().eval()
