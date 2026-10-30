"""Independent legal-softmax/value oracles. Tensor execution is Linux only."""

import hashlib
import math

import pytest


def test_evaluator_returns_legal_probabilities_and_unflipped_value_without_gradients():
    import torch

    from training.policy_value import TorchPolicyValue
    from training.tests.test_students import Position, model

    network = model().train()
    with torch.no_grad():
        network.logits[0, 0] = math.log(3)
    original = network.forward

    def forward(features):
        logits, _value = original(features)
        return logits, torch.tensor([[0.5]])

    network.forward = forward
    policy = TorchPolicyValue(network, device="cpu")
    priors, value = policy(Position())
    assert list(priors) == [0, 2] and priors == pytest.approx({0: 0.75, 2: 0.25})
    assert value == 0.5 and policy.calls == 1
    assert policy.model_sha256 is None and policy.binding is None
    assert not network.training and network.grad_enabled == [False]
    assert not network.logits.requires_grad and network.logits.grad is None


@pytest.mark.parametrize("value", [1.01, float("nan"), float("inf")])
def test_invalid_value_is_rejected_without_clamping(value):
    import torch

    from training.policy_value import TorchPolicyValue
    from training.tests.test_students import Position, model

    network = model()
    original = network.forward

    def forward(features):
        logits, _value = original(features)
        return logits, torch.tensor([[value]])

    network.forward = forward
    with pytest.raises(ValueError):
        TorchPolicyValue(network, device="cpu")(Position())


def test_missing_cuda_is_an_error_and_is_not_relabelled_cpu(monkeypatch):
    import torch

    from training.policy_value import TorchPolicyValue

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(ValueError, match="CUDA"):
        TorchPolicyValue(None, device="cuda")


def test_fp32_evaluator_disables_ambient_tf32_and_enables_determinism():
    import torch

    from training.policy_value import TorchPolicyValue
    from training.tests.test_students import Position, model

    before = (
        torch.are_deterministic_algorithms_enabled(),
        torch.backends.cuda.matmul.allow_tf32,
        torch.backends.cudnn.allow_tf32,
        torch.backends.cudnn.benchmark,
        torch.backends.cudnn.deterministic,
        torch.get_float32_matmul_precision(),
    )
    try:
        torch.use_deterministic_algorithms(False)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
        evaluator = TorchPolicyValue(model(), device="cpu")
        assert torch.are_deterministic_algorithms_enabled()
        assert (
            not torch.backends.cuda.matmul.allow_tf32
            and not torch.backends.cudnn.allow_tf32
        )
        assert not torch.backends.cudnn.benchmark and torch.backends.cudnn.deterministic
        assert torch.get_float32_matmul_precision() == "highest"
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.use_deterministic_algorithms(False)
        evaluator(Position())
        assert torch.are_deterministic_algorithms_enabled()
        assert (
            not torch.backends.cuda.matmul.allow_tf32
            and not torch.backends.cudnn.allow_tf32
        )
    finally:
        torch.use_deterministic_algorithms(before[0])
        torch.backends.cudnn.benchmark = before[3]
        torch.backends.cudnn.deterministic = before[4]
        torch.set_float32_matmul_precision(before[5])
        torch.backends.cuda.matmul.allow_tf32 = before[1]
        torch.backends.cudnn.allow_tf32 = before[2]


def test_cuda_requires_an_explicit_deterministic_workspace(monkeypatch):
    import torch

    from training.policy_value import TorchPolicyValue

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.delenv("CUBLAS_WORKSPACE_CONFIG", raising=False)
    with pytest.raises(ValueError, match="workspace"):
        TorchPolicyValue(None, device="cuda")


def test_file_loader_binds_the_actual_safetensors_hash_and_loads_all_weights(
    tmp_path, monkeypatch
):
    import torch
    from safetensors.torch import save_file

    import export.model
    from training.policy_value import load_policy_value
    from training.tests.test_students import Position, model

    original = model()
    with torch.no_grad():
        original.logits[0, 0] = math.log(3)
    path = tmp_path / "model.safetensors"
    save_file(original.state_dict(), path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    seeds = []

    def factory(seed):
        seeds.append(seed)
        return model()

    monkeypatch.setattr(export.model, "make_model", factory)
    policy = load_policy_value(path, expected_sha256=sha, device="cpu")
    assert policy.model_sha256 == sha
    assert policy.binding == {
        "artifact_sha256": sha,
        "architecture": "transformer-s-full-v1",
        "backend": "torch-cpu",
        "compute_dtype": "float32",
    }
    assert policy(Position())[0] == pytest.approx({0: 0.75, 2: 0.25})
    assert seeds == [314159]
    policy.binding["artifact_sha256"] = "b" * 64
    assert policy.binding["artifact_sha256"] == sha


@pytest.mark.parametrize(
    "kind", ["hash", "symlink", "dtype", "nonfinite", "missing-key"]
)
def test_loader_rejects_wrong_hash_symlink_precision_nonfinite_and_missing_weights(
    kind, tmp_path, monkeypatch
):
    import torch
    from safetensors.torch import save_file

    import export.model
    from training.policy_value import load_policy_value
    from training.tests.test_students import model

    network = model()
    state = network.state_dict()
    if kind == "dtype":
        state = {key: value.double() for key, value in state.items()}
    if kind == "nonfinite":
        state["logits"][0, 0] = float("nan")
    if kind == "missing-key":
        state = {"other": torch.zeros(1)}
    path = tmp_path / "model.safetensors"
    save_file(state, path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if kind == "symlink":
        link = tmp_path / "link.safetensors"
        link.symlink_to(path)
        path = link
    if kind == "hash":
        sha = "a" * 64
    constructed = []

    def factory(seed):
        constructed.append(seed)
        return model()

    monkeypatch.setattr(export.model, "make_model", factory)
    with pytest.raises(ValueError):
        load_policy_value(path, expected_sha256=sha, device="cpu")
    if kind != "missing-key":
        assert constructed == []


def test_file_change_during_loading_is_detected_before_binding(tmp_path, monkeypatch):
    import safetensors.torch

    import export.model
    from training.policy_value import load_policy_value
    from training.tests.test_students import model

    path = tmp_path / "model.safetensors"
    safetensors.torch.save_file(model().state_dict(), path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    original = safetensors.torch.load_file

    def changed(*args, **kwargs):
        state = original(*args, **kwargs)
        with path.open("ab") as stream:
            stream.write(b"changed")
        return state

    monkeypatch.setattr(safetensors.torch, "load_file", changed)
    monkeypatch.setattr(export.model, "make_model", lambda _seed: model())
    with pytest.raises(ValueError, match="changed"):
        load_policy_value(path, expected_sha256=sha, device="cpu")
