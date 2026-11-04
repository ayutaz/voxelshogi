"""Fixed deterministic PUCT32 inference for evaluation, without actor noise."""

from training.policy_value import load_policy_value
from training.selfplay_search import SearchConfig, search


class PuctPlayer:
    """The puct32-v1 name fixes 32 simulations, depth64 and cpuct1.0.

    No root noise, temperature sampling, reused tree or fallback move is used.
    The supplied evaluator returns legal priors and a side-to-move value.
    """

    def __init__(self, evaluate, *, stop_requested=lambda: False, observe_input=None):
        self.evaluate, self.stop_requested = evaluate, stop_requested
        self.observe_input = observe_input

    def __call__(self, game):
        evaluate = self.evaluate
        if self.observe_input is not None:

            def evaluate(position):
                self.observe_input(position)
                return self.evaluate(position)

        result = search(
            game,
            evaluate,
            SearchConfig(simulations=32, max_depth=64, cpuct=1.0),
            stop_requested=self.stop_requested,
        )
        if (
            self.stop_requested()
            or result["stop_reason"] != "simulations"
            or result["completed_simulations"] != 32
        ):
            raise InterruptedError("evaluation PUCT did not finish its fixed budget")
        action = result["best_action"]
        if type(action) is not int or action not in game.legal_actions():
            raise ValueError("evaluation PUCT returned an illegal action")
        return action


def load_puct_player(
    path, *, expected_sha256, device, stop_requested=lambda: False, observe_input=None
):
    evaluate = load_policy_value(path, expected_sha256=expected_sha256, device=device)
    return PuctPlayer(
        evaluate, stop_requested=stop_requested, observe_input=observe_input
    )
