"""Versioned comparison limits; M3 remains the default contract."""

TRAINED_NUMERIC_CONTRACT = "voxelshogi-trained-numeric-v1"
TOLERANCES = {"fp32": (1e-5, 1e-4), "fp16": (1e-3, 1e-2), "int8": (1e-5, 1e-4)}


def output_tolerances(precision, output="policy", numeric_contract=None):
    if precision not in TOLERANCES or output not in ("policy", "value"):
        raise ValueError("unknown numeric precision or output")
    if numeric_contract not in (None, TRAINED_NUMERIC_CONTRACT):
        raise ValueError("unknown numeric contract")
    if (
        numeric_contract == TRAINED_NUMERIC_CONTRACT
        and output == "policy"
        and precision in ("fp32", "int8")
    ):
        return 1e-4, 1e-4
    return TOLERANCES[precision]
