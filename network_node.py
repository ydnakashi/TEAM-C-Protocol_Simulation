from enum import Enum, auto

class NodeType(Enum):
    IRRESOLUTE = "irresolute node"
    ORDINARY = "ordinary node"
    SUBCLUSTER_HEAD = "subcluster head"
    CLUSTER_HEAD = "cluster head"
    BASE_STATION = "base station"

class EnergyConsumption(Enum): # All in nanojoules
    ENERGY_PER_BIT = 50
    ON_CONSUMPTION = auto()
    S_CH_CONSUMPTION = auto()
    CH_CONSUMPTION = auto()
    BASE_STATION_CONSUMPTION = auto()

class Node():
    def __init__(self, id: int, x: float, y: float) -> None:
        self.id: int = 0
        self.energy: float = 0.0
        self.own_worthiness_score: float = 0.0
        self.parent_worthiness_score: float = 0.0
        self.children_worthiness_score: list[tuple[int, float]] = []
        self.random_destruction_factor: float = 0.0
        self.coordinates: tuple[float, float] = (0.0, 0.0)
        self.parent: int = 0
        self.nodeType: NodeType = NodeType.IRRESOLUTE
     
    def get_worthiness_score(self) -> float:
        return self.own_worthiness_score
    
    def set_worthiness_score(self, score: float) -> None:
        self.own_worthiness_score = score

    def set_parent_worthiness_score(self, score: float) -> None:
        self.parent_worthiness_score = score
    
    def set_children_worthiness_score(self, child_id: int, score: float) -> None:
        self.children_worthiness_score.append((child_id, score))
    
    def consume_enery() -> None:
        consumption = 0.0
        if self.nodeType == NodeType.ORDINARY:
            consumption = EnergyConsumption.ON_CONSUMPTION.value
        elif self.nodeType == NodeType.SUBCLUSTER_HEAD:
            consumption = EnergyConsumption.S_CH_CONSUMPTION.value
        elif self.nodeType == NodeType.CLUSTER_HEAD:
            consumption = EnergyConsumption.CH_CONSUMPTION.value
        elif self.nodeType == NodeType.BASE_STATION:
            consumption = EnergyConsumption.BASE_STATION_CONSUMPTION.value
        self.energy -= consumption

