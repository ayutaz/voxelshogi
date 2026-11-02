"""Vast.ai inventory/destruction adapter for the independent deadline runner."""

import os
import re
import urllib.error

from training.vast_rental_control import VastClient, instance_inventory


class VastDeadlineApi:
    def __init__(self, api, *, tag):
        self.api, self.tag = api, tag
        self.observed, self.acknowledged = set(), set()

    def _inventory(self):
        rows = instance_inventory(self.api)
        if any(type(r.get("id")) is not int or r["id"] <= 0 for r in rows):
            raise ValueError("invalid Vast.ai instance identity")
        return rows

    def __call__(self, path, data):
        if path == "/api/v1/instances/list":
            if data != {
                "selector": {"ByTags": {"all": [self.tag], "any": []}},
                "mask": {"with_usage_info": False, "with_credentials": False},
            }:
                raise ValueError("Vast.ai deadline requires its exact ownership label")
            inventory = self._inventory()
            present = {r["id"] for r in inventory}
            selected = [r for r in inventory if r.get("label") == self.tag]
            if any(
                r["id"] in self.observed and r.get("label") != self.tag
                for r in inventory
            ):
                raise ValueError("Vast.ai deadline ownership label changed")
            self.observed.update(r["id"] for r in selected)
            # Vast deletion removes the row. Require both an explicit successful
            # destruction response and absence in a complete paginated inventory.
            rows = [
                {
                    "id": r["id"],
                    "tags": [self.tag],
                    "status": "Active",
                    "resources_released": False,
                }
                for r in selected
            ]
            rows.extend(
                {
                    "id": identity,
                    "tags": [self.tag],
                    "status": "Inactive",
                    "resources_released": True,
                }
                for identity in sorted(self.acknowledged - present)
            )
            return {"instances": rows}
        if (
            path != "/api/v1/instances/terminate"
            or set(data) != {"selector"}
            or set(data["selector"]) != {"ById"}
        ):
            raise ValueError("Vast.ai deadline has no rental operation")
        ids = data["selector"]["ById"]
        if (
            type(ids) is not list
            or not ids
            or len(set(ids)) != len(ids)
            or any(type(i) is not int or i not in self.observed for i in ids)
        ):
            raise ValueError("Vast.ai destruction requires previously owned IDs")
        current = {r["id"]: r for r in self._inventory()}
        for identity in ids:
            if identity not in current or current[identity].get("label") != self.tag:
                raise ValueError("Vast.ai destruction ownership label differs")
            response = self.api("DELETE", f"/api/v0/instances/{identity}")
            if response.get("success") is not True:
                raise RuntimeError("Vast.ai destruction not acknowledged")
            self.acknowledged.add(identity)
        return {}


def client(tag):
    key = os.environ.get("VAST_API_KEY")
    if not key:
        raise ValueError("Vast.ai control secret is missing")
    raw = VastClient(key)

    def restricted(method, path, data=None, params=None):
        if not (
            method == "GET"
            and path == "/api/v1/instances"
            or method == "DELETE"
            and re.fullmatch(r"/api/v0/instances/[1-9][0-9]*", path)
        ):
            raise ValueError("Vast.ai deadline cannot create or alter a rental")
        try:
            return raw(method, path, data, params)
        except urllib.error.URLError, TimeoutError, OSError, RuntimeError:
            raise RuntimeError("Vast.ai guard request failed") from None

    return VastDeadlineApi(restricted, tag=tag)


if __name__ == "__main__":
    from training.remote_deadline import main

    main(provider="vast")
