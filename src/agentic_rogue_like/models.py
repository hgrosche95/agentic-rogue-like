"""Core state models for a run.

These are the contracts everything else builds on: the deterministic game
loop (Phase 1) reads and writes them directly, and later the encounter agent
(Phase 2) fills them in via constrained tool calls instead of free text -
so the shape defined here is also the schema the LLM is allowed to produce.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    COMBAT = "combat"
    ELITE = "elite"
    EVENT = "event"
    SHOP = "shop"
    REST = "rest"
    BOSS = "boss"


class RunStatus(StrEnum):
    ONGOING = "ongoing"
    VICTORY = "victory"
    DEFEAT = "defeat"


class Relic(BaseModel):
    id: str
    name: str
    description: str


class Card(BaseModel):
    id: str
    name: str
    cost: int
    description: str


class PlayerState(BaseModel):
    hp: int
    max_hp: int
    attack: int = 5
    gold: int = 0
    relics: list[Relic] = Field(default_factory=list)
    deck: list[Card] = Field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0


class Enemy(BaseModel):
    id: str
    name: str
    hp: int
    attack: int


class MapNode(BaseModel):
    id: str
    floor: int
    type: NodeType
    connections: list[str] = Field(default_factory=list)
    visited: bool = False


class RunState(BaseModel):
    seed: int
    floor: int = 0
    status: RunStatus = RunStatus.ONGOING
    player: PlayerState
    nodes: dict[str, MapNode] = Field(default_factory=dict)
    current_node_id: str | None = None
    history: list[str] = Field(default_factory=list)
