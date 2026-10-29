"""Hand-computed small scalars test M6 policy cancellation without any model."""

import numpy as np
import pytest

from export.contract import compare_outputs
from export.numeric import TRAINED_NUMERIC_CONTRACT, output_tolerances

M6 = "voxelshogi-trained-numeric-v1"


def test_only_trained_policy_gets_the_predeclared_absolute_roundoff_bound():
    assert TRAINED_NUMERIC_CONTRACT == M6
    for precision in ("fp32", "int8"):
        assert output_tolerances(precision, "policy", M6) == (0.0001, 0.0001)
        assert output_tolerances(precision, "value", M6) == (0.00001, 0.0001)
        assert output_tolerances(precision, "policy") == (0.00001, 0.0001)
    assert output_tolerances("fp16", "policy", M6) == (0.001, 0.01)
    assert output_tolerances("fp16", "value", M6) == (0.001, 0.01)


@pytest.mark.parametrize("precision", ["fp32", "int8"])
def test_near_zero_trained_policy_is_bounded_without_widening_value_or_m3(precision):
    expected = np.array([0.0, 0.01])
    actual = np.array([0.00009, 0.01009])
    result = compare_outputs(expected, actual, precision=precision, numeric_contract=M6)
    assert result["exceeded"] == 0 and result["elements"] == 2
    assert result["atol"] == 0.0001 and result["rtol"] == 0.0001
    assert result["max_abs"] == pytest.approx(0.00009)
    with pytest.raises(ValueError, match="outputs exceed"):
        compare_outputs(expected, actual, precision=precision)
    with pytest.raises(ValueError, match="outputs exceed"):
        compare_outputs(
            expected, actual, precision=precision, output="value", numeric_contract=M6
        )


def test_single_bad_element_cannot_hide_in_an_average_or_wider_relative_error():
    with pytest.raises(ValueError, match="1/3 outputs exceed fp32 tolerance"):
        compare_outputs(np.zeros(3), np.array([0.0, 0.0, 0.00011]), numeric_contract=M6)
    for contract in (None, M6):
        result = compare_outputs(
            np.zeros(1), np.array([0.0009]), precision="fp16", numeric_contract=contract
        )
        assert result["atol"] == 0.001 and result["rtol"] == 0.01
        with pytest.raises(ValueError, match="outputs exceed"):
            compare_outputs(
                np.zeros(1),
                np.array([0.0011]),
                precision="fp16",
                numeric_contract=contract,
            )


def test_unknown_contract_output_or_precision_cannot_select_a_permissive_default():
    for args in [
        ("fp32", "policy", "other"),
        ("fp32", "other", M6),
        ("other", "policy", M6),
    ]:
        with pytest.raises(ValueError):
            output_tolerances(*args)
