"""Visit-distribution losses with full legal normalization and explicit value kind.

Only call on external Linux. Importing the module does not initialize Torch.
Source records/provenance must be verified before these numerical loss terms.
"""

import math

from training.learning import _legal_indices
from training.research_targets import visit_policy


def loss_terms(
    logits,
    values,
    policies,
    value_targets,
    legal_actions,
    *,
    value_kind,
    value_weight=1.0,
):
    import torch
    from torch.nn import functional as F

    if (
        logits.ndim != 2
        or not len(logits)
        or not logits.shape[1]
        or values.shape != (len(logits), 1)
        or not isinstance(policies, (list, tuple))
        or not isinstance(value_targets, (list, tuple))
        or not isinstance(legal_actions, (list, tuple))
        or any(
            len(items) != len(logits)
            for items in (policies, value_targets, legal_actions)
        )
        or values.device != logits.device
        or any(not torch.is_floating_point(x) for x in (logits, values))
        or any(not torch.isfinite(x).all().item() for x in (logits, values))
        or value_kind not in ("terminal-v1", "bootstrap-v1", "search-score-v1")
        or type(value_weight) not in (int, float)
        or not math.isfinite(value_weight)
        or not 0 <= value_weight <= 100
    ):
        raise ValueError("invalid research loss tensors, sizes, value kind, or weight")
    for policy, label, legal in zip(
        policies, value_targets, legal_actions, strict=True
    ):
        if not isinstance(policy, dict) or set(policy) != {
            "kind",
            "actions",
            "probabilities",
            "visits",
            "total_visits",
        }:
            raise ValueError("a verified visit-distribution policy is required")
        if (
            not isinstance(policy["actions"], list)
            or not isinstance(policy["visits"], list)
            or type(policy["total_visits"]) is not int
            or not isinstance(policy["probabilities"], list)
            or any(type(p) not in (int, float) for p in policy["probabilities"])
            or len(set(policy["actions"])) != len(policy["actions"])
            or policy
            != visit_policy(
                legal, dict(zip(policy["actions"], policy["visits"], strict=True))
            )
        ):
            raise ValueError("policy probabilities differ from completed legal visits")
        if (
            not isinstance(label, dict)
            or label.get("kind") != value_kind
            or type(label.get("value")) not in (int, float)
            or not math.isfinite(label["value"])
            or not -1 <= label["value"] <= 1
        ):
            raise ValueError("mixed, nonfinite, or invalid value target")
    representatives = torch.tensor(
        [p["actions"][0] for p in policies], device=logits.device, dtype=torch.long
    )
    indices = _legal_indices(logits, representatives, legal_actions)
    terms = []
    for i, legal in enumerate(indices):
        log_probabilities = F.log_softmax(logits[i, legal], dim=0)
        locations = {action: index for index, action in enumerate(legal.tolist())}
        selected = torch.tensor(
            [locations[a] for a in policies[i]["actions"]],
            device=logits.device,
            dtype=torch.long,
        )
        weights = torch.tensor(
            policies[i]["probabilities"], device=logits.device, dtype=logits.dtype
        )
        terms.append(-(weights * log_probabilities[selected]).sum())
    policy = torch.stack(terms).mean()
    targets = torch.tensor(
        [label["value"] for label in value_targets],
        device=values.device,
        dtype=values.dtype,
    )
    value = F.mse_loss(values[:, 0], targets, reduction="mean")
    return {"policy": policy, "value": value, "total": policy + value_weight * value}
