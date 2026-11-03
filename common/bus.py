"""Event bus shared by all services.

Tests and local runs use the in-memory bus. Set BUS_URL=redis://... in
docker-compose to fan events out through Redis instead.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Callable

Handler = Callable[[dict[str, Any]], None]


class InMemoryBus:
    def __init__(self) -> None:
        self.handlers: dict[str, list[Handler]] = defaultdict(list)
        self.log: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, topic: str, handler: Handler) -> None:
        self.handlers[topic].append(handler)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.log.append((topic, payload))
        for h in list(self.handlers[topic]):
            h(payload)


class RedisBus(InMemoryBus):  # pragma: no cover - exercised in docker-compose
    def __init__(self, url: str) -> None:
        super().__init__()
        import redis  # type: ignore
        self.r = redis.Redis.from_url(url)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        super().publish(topic, payload)
        self.r.publish(topic, json.dumps(payload))


bus: InMemoryBus = RedisBus(os.environ["BUS_URL"]) if os.getenv("BUS_URL") else InMemoryBus()
