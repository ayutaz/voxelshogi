"""Small CPU arithmetic oracle in Linux CI, never evidence of real CUDA."""


def test_kernel_probe_matches_independent_integer_matrix_and_gradients():
    from training.cuda_preflight import kernel_probe

    assert kernel_probe("cpu") == {
        "device": "cpu",
        "product": [[19.0, 22.0], [43.0, 50.0]],
        "left_gradient": [[11.0, 15.0], [11.0, 15.0]],
        "right_gradient": [[4.0, 4.0], [6.0, 6.0]],
    }
