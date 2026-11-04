"""Fixed four-RTX5090 admission, including a conservative network reservation."""

import math

from training.vast_rental_control import quote_offer
from training.vast_research_control import ResearchVastRental, main

MAXIMUM_HOURLY_USD = 3.5
TRANSFER_RESERVE_USD = 1
ESTIMATED_DOWNLOAD_GB = 40
ESTIMATED_UPLOAD_GB = 10


def quote_four_gpu(offer):
    """Validate the physical four-GPU host and price shared storage only once.

    Transfer prices are USD/GB, per the official search API. The 50GB estimate
    includes dependency/bootstrap and fixed-artifact traffic with ample margin;
    this is a reservation, not a provider-enforced network or spend limit.
    """
    if type(offer.get("num_gpus")) is not int or offer["num_gpus"] != 4:
        raise ValueError("four identical RTX5090 GPUs required")
    for field in ("inet_up_cost", "inet_down_cost"):
        value = offer.get(field)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 0.01
        ):
            raise ValueError("unquoted four-GPU transfer price")
    normalized = dict(offer)
    normalized["num_gpus"] = 1
    try:
        for field in (
            "dph_base",
            "dph_total",
            "storage_total_cost",
            "cpu_ram",
            "cpu_cores_effective",
        ):
            if type(offer[field]) not in (int, float) or not math.isfinite(
                offer[field]
            ):
                raise ValueError("invalid four-GPU numeric facts")
            normalized[field] = offer[field] / 4
    except (TypeError, KeyError) as error:
        raise ValueError("invalid four-GPU quote fields") from error
    normalized["inet_up_cost"] = normalized["inet_down_cost"] = 0
    per_gpu = quote_offer(normalized)
    hourly = per_gpu["hourly_usd"] * 4
    estimate = (
        ESTIMATED_DOWNLOAD_GB * offer["inet_down_cost"]
        + ESTIMATED_UPLOAD_GB * offer["inet_up_cost"]
    )
    if hourly > MAXIMUM_HOURLY_USD or estimate > TRANSFER_RESERVE_USD:
        raise ValueError("four-GPU compute/transfer quote exceeds reservation")
    return {
        "offer_id": offer["id"],
        "gpu": "RTX 5090",
        "num_gpus": 4,
        "disk_gb": per_gpu["disk_gb"],
        "hourly_usd": hourly,
        "inet_up_usd_per_gb": offer["inet_up_cost"],
        "inet_down_usd_per_gb": offer["inet_down_cost"],
        "estimated_download_gb": ESTIMATED_DOWNLOAD_GB,
        "estimated_upload_gb": ESTIMATED_UPLOAD_GB,
        "estimated_transfer_usd": estimate,
        "transfer_reserve_usd": TRANSFER_RESERVE_USD,
        "bandwidth": "metered; fixed-workload estimate plus conservative reserve",
    }


class DistributedVastRental(ResearchVastRental):
    PLAN_SCHEMA = "voxelshogi-vast-distributed-plan-v1"
    HARDWARE_FIELDS = {"offer_id", "disk_gb", "maximum_transfer_usd"}
    NUM_GPUS = 4
    MAXIMUM_HOURLY_USD = MAXIMUM_HOURLY_USD
    OFFER_QUOTER = staticmethod(quote_four_gpu)
    GUARD_MODULE = "training.vast_distributed_control"

    def validate_hardware(self, plan):
        super().validate_hardware(plan)
        if (
            self.phase != "phase5"
            or plan["purpose"] != "phase5-distributed"
            or type(plan["maximum_transfer_usd"]) not in (int, float)
            or plan["maximum_transfer_usd"] != TRANSFER_RESERVE_USD
        ):
            raise ValueError("separate distributed purpose/transfer reserve required")
        return "vast"

    def cost_cap(self, plan):
        return super().cost_cap(plan) + plan["maximum_transfer_usd"]

    def minimum_credit(self, quote, plan):
        return super().minimum_credit(quote, plan) + plan["maximum_transfer_usd"]


if __name__ == "__main__":
    main(control_type=DistributedVastRental)
