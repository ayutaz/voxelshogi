"""Actual fixed-M best-checkpoint export on Linux CI; no training claim."""

import json

from training.tests.test_research_selection import records


def test_actual_M_export_uses_selected_checkpoint_not_latest_or_constructor(tmp_path):
    import torch
    from safetensors.torch import load_file

    from export.research_contract import architecture_config
    from export.research_model import make_research_model
    from training.checkpoint import save_checkpoint
    from training.research_selection import export_selected_weights
    from training.research_weights import research_metadata

    torch.set_num_threads(1)
    binding, latest, best, events, _ = records()
    binding["config"]["device"] = "cpu"
    binding["environment"]["device"] = "cpu"
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
    )
    (run / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    model = make_research_model(architecture_config("full"), seed=67003)
    optimizer = torch.optim.AdamW(model.parameters())
    with torch.no_grad():
        model.position[0, 0, 0] += 0.25
    selected = model.position.detach().clone()
    save_checkpoint(
        run / "checkpoints",
        model,
        optimizer,
        progress=best["progress"],
        binding=binding,
        best=True,
    )
    with torch.no_grad():
        model.position[0, 0, 0] += 0.5
    save_checkpoint(
        run / "checkpoints",
        model,
        optimizer,
        progress=latest["progress"],
        binding=binding,
    )
    out = tmp_path / "selected"
    receipt = export_selected_weights(run, out, expected_binding=binding)
    actual = load_file(out / "model.safetensors")
    assert torch.equal(actual["position"], selected)
    assert not torch.equal(actual["position"], model.position)
    assert receipt["weights"]["metadata"]["step"] == 2
    assert (
        research_metadata(out / "model.safetensors") == receipt["weights"]["metadata"]
    )
    assert receipt["inference_publication_approved"] is False
