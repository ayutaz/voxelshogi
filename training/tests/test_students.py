"""Linux CPU tensor inference with independent illegal-logit/tie oracles."""

import pytest


class Position:
    def legal_actions(self):
        return {2: "opaque-two", 0: "opaque-zero"}

    def features(self):
        import numpy as np

        return np.zeros((729, 43), dtype=np.float32)


def model():
    import torch
    from torch import nn

    class Logits(nn.Module):
        def __init__(self):
            super().__init__()
            self.logits = nn.Parameter(torch.zeros(1, 1067985))
            self.grad_enabled = []
            with torch.no_grad():
                self.logits[0, 1] = 1000  # Illegal maximum must never win.

        def forward(self, features):
            self.grad_enabled.append(torch.is_grad_enabled())
            assert features.shape == (1, 729, 43)
            return self.logits, torch.zeros(1, 1)

    return Logits()


def test_student_infers_without_grad_and_uses_legal_canonical_minimum_on_ties():
    import torch

    from training.students import TorchStudent

    network = model().train()
    student = TorchStudent(network, device="cpu")
    assert student(Position()) == 0
    with torch.no_grad():
        network.logits[0, 0] = -1
    assert student(Position()) == 2
    assert network.grad_enabled == [False, False] and not network.training
    assert network.logits.grad is None
    with torch.no_grad():
        network.logits[0, 1] = float("nan")
    with pytest.raises(ValueError):
        student(Position())


def test_ort_wrapper_preserves_batch1_fp32_contract_and_uses_same_selection():
    import numpy as np
    import torch

    from training.students import TorchStudent, make_ort_model

    calls = []

    class Session:
        def run(self, names, feeds):
            assert names == ["policy", "value"]
            assert (
                feeds["features"].shape == (1, 729, 43)
                and feeds["features"].dtype == np.float32
            )
            calls.append(1)
            logits = np.zeros((1, 1067985), dtype=np.float32)
            logits[0, 1] = 1000
            return logits, np.zeros((1, 1), dtype=np.float32)

    network = make_ort_model(None, precision="int8", session=Session())
    assert TorchStudent(network, device="cpu")(Position()) == 0 and calls == [1]
    with pytest.raises(ValueError):
        TorchStudent(network, device="cuda")
    with pytest.raises(ValueError):
        network(torch.zeros(2, 729, 43))
    with pytest.raises(ValueError):
        make_ort_model(None, precision="unknown", session=Session())
