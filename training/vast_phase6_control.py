"""Priced single-GPU Phase6 jobs inside the same reviewed USD200 ledger."""

from training.vast_evaluation_control import TRANSFER_RESERVE_USD, EvaluationVastRental
from training.vast_research_control import ResearchVastRental, main


class Phase6VastRental(EvaluationVastRental):
    PLAN_SCHEMA = "voxelshogi-vast-phase6-plan-v1"
    GUARD_MODULE = "training.vast_phase6_control"

    def validate_hardware(self, plan):
        ResearchVastRental.validate_hardware(self, plan)
        if (
            self.phase != "phase6"
            or plan["purpose"]
            not in ("phase6-operators", "phase6-training", "phase6-publication")
            or type(plan["maximum_transfer_usd"]) not in (int, float)
            or plan["maximum_transfer_usd"] != TRANSFER_RESERVE_USD
        ):
            raise ValueError(
                "separate Phase6 purpose and priced transfer reserve required"
            )
        return "vast"


if __name__ == "__main__":
    main(control_type=Phase6VastRental)
