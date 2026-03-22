from enum import Enum, auto

class NodeType(Enum):
    IRRESOLUTE = 4
    ORDINARY = 3
    SUBCLUSTER_HEAD = 2
    CLUSTER_HEAD = 1
    BASE_STATION = 0

class EnergyConsumption(Enum): # All in nanojoules
    ENERGY_PER_BIT = 50 # nj/bit
    EPSILON_FS = 0.01   # nj/bit/m^2
    ENERGY_DA = 5 # nj/bit/signal
    EPSILON_AMP = 0.0000013 # nj/bit/m^4
    DISTANCE_LIMIT = 10 # m

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

