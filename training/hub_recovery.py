"""Bounded metadata reads and reconciliation of uncertain HF setup writes.

The publication harness still validates destination, public/manual, Community
OFF, inventory and immutable hashes. Uploads are never automatically retried.
Callers retain ownership of process/network timeouts and host retirement.
"""

import math
import time


class RecoveryApi:
    def __init__(
        self,
        api,
        *,
        deadline,
        transient_errors,
        clock=time.time,
        wait=time.sleep,
        stop_requested=lambda: False,
        observe=lambda _: None,
    ):
        if (
            type(deadline) not in (int, float)
            or not math.isfinite(deadline)
            or type(transient_errors) is not tuple
            or not transient_errors
            or any(
                not isinstance(cls, type)
                or not issubclass(cls, Exception)
                or issubclass(ValueError, cls)
                or issubclass(RuntimeError, cls)
                for cls in transient_errors
            )
        ):
            raise ValueError(
                "finite fixed deadline and narrow transport errors required"
            )
        self.api, self.deadline, self.transient_errors = api, deadline, transient_errors
        self.clock, self.wait = clock, wait
        self.stop_requested, self.observe = stop_requested, observe

    def __getattr__(self, name):
        return getattr(self.api, name)

    def _check(self):
        if self.stop_requested() or self.clock() >= self.deadline:
            raise InterruptedError("fixed HF operation deadline or stop")

    def _read(self, name, **kwargs):
        for attempt in range(1, 4):
            self._check()
            self.observe({"operation": name, "attempt": attempt})
            try:
                result = getattr(self.api, name)(**kwargs)
            except self.transient_errors:
                if attempt == 3:
                    raise
                delay = 2**attempt
                if self.clock() + delay >= self.deadline:
                    raise InterruptedError(
                        "HF read backoff exceeds fixed deadline"
                    ) from None
                self.wait(delay)
            else:
                self._check()
                return result

    def _write(self, name, kwargs, confirm=None):
        self._check()
        self.observe({"operation": name, "attempt": 1})
        try:
            result = getattr(self.api, name)(**kwargs)
        except self.transient_errors:
            self._check()
            if confirm is None or confirm() is not True:
                raise
            return None
        self._check()
        return result

    def whoami(self, **kwargs):
        return self._read("whoami", **kwargs)

    def repo_exists(self, **kwargs):
        return self._read("repo_exists", **kwargs)

    def repo_info(self, **kwargs):
        return self._read("repo_info", **kwargs)

    def community_disabled(self, **kwargs):
        return self._read("community_disabled", **kwargs)

    def create_repo(self, **kwargs):
        destination = {k: kwargs[k] for k in ("repo_id", "repo_type")}
        return self._write(
            "create_repo", kwargs, lambda: self.repo_exists(**destination)
        )

    def update_repo_settings(self, **kwargs):
        destination = {k: kwargs[k] for k in ("repo_id", "repo_type")}
        if (
            set(kwargs) != {"repo_id", "repo_type", "gated"}
            or kwargs["gated"] != "manual"
        ):
            raise ValueError("only manual gate reconciliation is supported")
        return self._write(
            "update_repo_settings",
            kwargs,
            lambda: self.repo_info(**destination).gated == "manual",
        )

    def disable_community(self, **kwargs):
        return self._write(
            "disable_community", kwargs, lambda: self.community_disabled(**kwargs)
        )

    def upload_folder(self, **kwargs):
        return self._write("upload_folder", kwargs)
