"""Independent hand fixtures; no Torch, dataset, CUDA or actual checkpoints."""

import copy
import runpy

module = runpy.run_path("infrastructure/research/pilot/resume_proof.py")


class Tensor:
    def __init__(self, values, *, dtype="float32", shape=(2,)):
        self.values, self.dtype, self.shape = values, dtype, shape

    def equal(self, other):
        return self.values == other.values


state = {
    "model": {"weight": Tensor([1, 2])},
    "optimizer": {"state": {0: {"step": Tensor([7]), "momentum": Tensor([3, 4])}}},
    "rng": {"python": (3, (1, 2), None), "cuda": [Tensor([5, 6])]},
    "progress": {"step": 7},
    "binding": {"seed": 42, "device": "cuda"},
}
compare = module["compare_tree"]
counts = compare(state, copy.deepcopy(state), Tensor)
assert counts == {"tensors": 4, "scalars": 7}
for changed in (
    {**state, "progress": {"step": 6}},
    {**state, "binding": {"seed": 43, "device": "cuda"}},
    {**state, "rng": {"python": (3, (1, 2), None), "cuda": [Tensor([6, 5])]}},
    {**state, "model": {"weight": Tensor([1, 2], dtype="float16")}},
    {**state, "model": {"weight": Tensor([1, 2], shape=(1, 2))}},
    {
        **state,
        "optimizer": {"state": {0: {"step": Tensor([6]), "momentum": Tensor([3, 4])}}},
    },
    {**state, "extra": 0},
    {**state, "progress": {"step": 7.0}},
):
    try:
        compare(state, changed, Tensor)
    except ValueError:
        pass
    else:
        raise AssertionError("changed checkpoint state admitted")
try:
    module["verify_runs"]("opaque", "opaque", total_updates=7)
except ValueError as error:
    assert "external Linux" in str(error)
else:
    raise AssertionError("Mac reached real checkpoint operations")
print(
    "Exact tree checks: weights/optimizer/RNG/progress/binding, dtype/shape/scalar type; Mac before numerics. Actual checkpoints0"
)
