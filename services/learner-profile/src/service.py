"""Learner profile service."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopicProficiency:
    topic: str
    level: str  # not_started, in_progress, mastered
    score: float = 0.0


@dataclass
class LearnerProfile:
    user_id: str
    display_name: str = ""
    topics: list[TopicProficiency] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)


class LearnerProfileService:
    def __init__(self, store: dict[str, LearnerProfile] | None = None) -> None:
        self._store = store if store is not None else {}

    def get_or_create(self, user_id: str) -> LearnerProfile:
        if user_id not in self._store:
            self._store[user_id] = LearnerProfile(user_id=user_id)
        return self._store[user_id]

    def update_profile(self, user_id: str, data: dict[str, Any]) -> LearnerProfile:
        profile = self.get_or_create(user_id)
        if "display_name" in data:
            profile.display_name = data["display_name"]
        if "preferences" in data:
            profile.preferences.update(data["preferences"])
        return profile

    def update_topic(self, user_id: str, topic: str, level: str, score: float) -> None:
        profile = self.get_or_create(user_id)
        for t in profile.topics:
            if t.topic == topic:
                t.level = level
                t.score = score
                return
        profile.topics.append(TopicProficiency(topic=topic, level=level, score=score))

    def get_progress(self, user_id: str) -> dict[str, Any]:
        profile = self.get_or_create(user_id)
        mastered = [t.topic for t in profile.topics if t.level == "mastered"]
        in_progress = [t.topic for t in profile.topics if t.level == "in_progress"]
        not_started = [t.topic for t in profile.topics if t.level == "not_started"]
        return {
            "user_id": user_id,
            "mastered": mastered,
            "in_progress": in_progress,
            "not_started": not_started,
            "topics": [{"topic": t.topic, "level": t.level, "score": t.score} for t in profile.topics],
        }
