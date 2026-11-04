"""Single RTX5090 evaluation with explicitly priced and reserved transfers."""

import math

from training.vast_rental_control import quote_offer
from training.vast_research_control import ResearchVastRental, main

MAXIMUM_HOURLY_USD = 0.75
TRANSFER_RESERVE_USD = 0.5
ESTIMATED_DOWNLOAD_GB = 40
ESTIMATED_UPLOAD_GB = 10


def quote_evaluation(offer):
    """Retain verified hardware requirements and price each traffic direction."""
    if type(offer.get("num_gpus")) is not int or offer["num_gpus"] != 1:
        raise ValueError("exactly one RTX5090 required")
    for field in ("inet_up_cost", "inet_down_cost"):
        value = offer.get(field)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 0.01
        ):
            raise ValueError("unquoted evaluation transfer price")
    normalized = {**offer, "inet_up_cost": 0, "inet_down_cost": 0}
    checked = quote_offer(normalized)
    estimate = (
        ESTIMATED_DOWNLOAD_GB * offer["inet_down_cost"]
        + ESTIMATED_UPLOAD_GB * offer["inet_up_cost"]
    )
    if checked["hourly_usd"] > MAXIMUM_HOURLY_USD or estimate > TRANSFER_RESERVE_USD:
        raise ValueError("evaluation compute/transfer exceeds reservation")
    return {
        "offer_id": offer["id"],
        "gpu": "RTX 5090",
        "num_gpus": 1,
        "disk_gb": checked["disk_gb"],
        "hourly_usd": checked["hourly_usd"],
        "inet_up_usd_per_gb": offer["inet_up_cost"],
        "inet_down_usd_per_gb": offer["inet_down_cost"],
        "estimated_download_gb": ESTIMATED_DOWNLOAD_GB,
        "estimated_upload_gb": ESTIMATED_UPLOAD_GB,
        "estimated_transfer_usd": estimate,
        "transfer_reserve_usd": TRANSFER_RESERVE_USD,
        "bandwidth": "metered; fixed-workload estimate plus conservative reserve",
    }


class EvaluationVastRental(ResearchVastRental):
    PLAN_SCHEMA = "voxelshogi-vast-evaluation-plan-v1"
    HARDWARE_FIELDS = {"offer_id", "disk_gb", "maximum_transfer_usd"}
    NUM_GPUS = 1
    MAXIMUM_HOURLY_USD = MAXIMUM_HOURLY_USD
    OFFER_QUOTER = staticmethod(quote_evaluation)
    GUARD_MODULE = "training.vast_evaluation_control"

    def validate_hardware(self, plan):
        super().validate_hardware(plan)
        if (
            self.phase != "phase5"
            or plan["purpose"]
            not in ("phase5-evaluation", "phase5-data", "phase5-selfplay")
            or type(plan["maximum_transfer_usd"]) not in (int, float)
            or plan["maximum_transfer_usd"] != TRANSFER_RESERVE_USD
        ):
            raise ValueError("separate Phase5 purpose/transfer reserve required")
        return "vast"

    def cost_cap(self, plan):
        return super().cost_cap(plan) + plan["maximum_transfer_usd"]

    def minimum_credit(self, quote, plan):
        return super().minimum_credit(quote, plan) + plan["maximum_transfer_usd"]


if __name__ == "__main__":
    main(control_type=EvaluationVastRental)
