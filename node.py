from dataclasses import dataclass
from enum import Enum, auto
import math
import sys

class NodeType(Enum):
    IRRESOLUTE = 4
    ORDINARY = 3
    SUBCLUSTER_HEAD = 2
    CLUSTER_HEAD = 1
    BASE_STATION = 0
    ASLEEP = None
    DEAD = 5

# (fill_color, alpha, scatter_size)
STATE_STYLE: dict[NodeType, tuple[str, float, int]] = {
    NodeType.ASLEEP:   ("#45475a", 0.55, 130),
    # NodeType.AWAKE:    ("#f9e2af", 0.85, 200),
    NodeType.IRRESOLUTE:       ("#fab387", 0.80, 200),
    NodeType.CLUSTER_HEAD:       ("#f38ba8", 1.00, 600),
    NodeType.SUBCLUSTER_HEAD:      ("#cba6f7", 1.00, 380),
    NodeType.ORDINARY: ("#89b4fa", 1.00, 260),
    NodeType.DEAD:     ("#1e1e2e", 0.65, 100),
}

class EnergyConsumption(Enum): # All in nanojoules
    ENERGY_PER_BIT = 50.0 # nj/bit
    EPSILON_FS = 0.01   # nj/bit/m^2
    ENERGY_DA = 5.0 # nj/bit/signal
    EPSILON_AMP = 0.0000013 # nj/bit/m^4

@dataclass
class Child:
    """A node that sends packets to its parent. Seen from the view of the parent."""
    state: NodeType
    tdma_slot: int = -1    # -1 means no slot given
    # received: bool = False
    overall_score: float = 0
    L: int = 0
    N: int = 0

class Action(Enum):
    SEND_DATA = auto()
    SEND_DATA_ACK = auto() 
    IDLE = auto()
    ELECTION = auto()

class Node:
    def __init__(self, id, power=100.0, coords=[0,0], bsCoords=[0,0], Rc=2):
        self.id: int = id
        self.state: NodeType = None
        self.power: float = power
        self.coords: tuple(int, int) = coords
        self.worthiness: float = 1
        self.overall_score: float = 1
        self.BScoords: tuple(int, int) = bsCoords # x, y

        self.chdList: dict[int, Child] = {}
        self.neighbourList: list[tuple(Node, float)] = []
        self.broadcastList: list[tuple(Node, float)] = []
        self.relayList: list[tuple(Node, float)] = []
        self.parent = Parent()

        self.twait = 0
        self.Rc = Rc

        self.label=f"Node {self.id}"
      
        self.action = Action.IDLE
        self.pkt = None
        self.timer = -1
        self.tdmaSlot = -1  # Default to -1 to represent no slot
        self.totalSlots = -1  # Default to -1 to represent no slot
        self.waiting = 0

    def broadcast (self, message):
        # print(f"Node {self.id} received:", message)

        # get all nodes within the Rc distance
        if(message['type'] == "STATE"):
            for neighbour, dist in self.neighbourList:
                neighbour.receive(self, message)
                self.consume_energy(sys.getsizeof(message), dist)
            if self.state == NodeType.CLUSTER_HEAD:
                for neighbour, dist in self.broadcastList:
                    neighbour.receive(self, message)
                    self.consume_energy(sys.getsizeof(message), dist)
        if(message['type'] == "MEMBERJOIN"):
            self.parent.node.receive(self, message)

        if(message['type'] == "CHROUTE"):
            for neighbour, dist in self.neighbourList:
                neighbour.receive(self, message, -1)
                self.consume_energy(sys.getsizeof(message), dist)

    def receive(self, sender, message):
        # helper function
        def find_index_by_senderId(tuples_list, first_elem):
            for i, t in enumerate(tuples_list):
                if t[0].id == first_elem:
                    return i
            return -1

        def float_node(tuples_list, nodeId):
            index = find_index_by_senderId(tuples_list, nodeId)
            if index == -1:
                return "floating failed"
            tup = tuples_list.pop(index)
            tuples_list.insert(0, tup)
            return None

        # direct neighbour   
        if message["type"] == "STATE":
            senderId = message["sender"]
            if senderId in [t[0].id for t in self.neighbourList]:
                # float latest STATE message sender to top to make sure former IR nodes are selected for parent CH
                float_node(self.neighbourList, senderId)

                # State selection
                if self.state == None:
                    if message['state'] == NodeType.CLUSTER_HEAD:
                        self.state = NodeType.SUBCLUSTER_HEAD
                        self.broadcast(message={
                            "type": "STATE",
                            "sender": self.id,
                            "state": NodeType.SUBCLUSTER_HEAD})
                    elif message['state'] == NodeType.SUBCLUSTER_HEAD:
                        self.state = NodeType.ORDINARY

            elif senderId in [t[0].id for t in self.broadcastList]:
                # float latest STATE message sender to top to make sure former IR nodes are selected for parent CH
                float_node(self.broadcastList, senderId)

                # State selection
                if self.state == None:
                    self.state = NodeType.IRRESOLUTE

        if message["type"] == "MEMBERJOIN":
            self.chdList[message['id']] = Child(state=message['state'])

        if message["type"] == "CHROUTE":
            if self.state == NodeType.CLUSTER_HEAD or self.state == NodeType.BASE_STATION: 
                dist = math.sqrt((self.coords[0]-0)**2 + (self.coords[1]- 0)**2)
                sender.receive(message= {
                    "type": "CHRETURN",
                    "dist": dist
                })
                
        if message["type"] == "CHRETURN":
            if message.dist > self.currentBSDist:
                self.parent.node = sender

        
    def neighbourCount(self):
        return len(self.neighbourList)

    # icd used to calcualte twait time
    # euclidan distance of all the nodes in its neighbour array
    def calculateICD(self, distance_matrix):
        if not self.neighbourList:
            return 0

        total = 0
        for neighbour in self.neighbourList:
            total += distance_matrix[self.id][neighbour.id]

        return total / len(self.neighbourList)
    
    def calculateWorthiness(self):
        print('test')

    def consume_energy(self, k: int, d: float) -> None:
        consumption = 0.0
        if self.state == NodeType.BASE_STATION:
            consumption = 0
        elif self.state == NodeType.CLUSTER_HEAD:
            consumption = (len(self.chdList) + 1) * k * (EnergyConsumption.ENERGY_PER_BIT.value + EnergyConsumption.ENERGY_DA.value) + EnergyConsumption.EPSILON_FS.value * k * d**2
        elif self.state == NodeType.SUBCLUSTER_HEAD:
            consumption = (len(self.chdList) + 1) * k * (EnergyConsumption.ENERGY_PER_BIT.value + EnergyConsumption.ENERGY_DA.value) + EnergyConsumption.EPSILON_AMP.value * k * d**4
        else:
            consumption = EnergyConsumption.ENERGY_PER_BIT.value * k + EnergyConsumption.EPSILON_FS.value * k * d**2
        self.power -= consumption

@dataclass
class Parent:
    node: Node = None
    L: int = 0
    N: int = 0
    overall_score: float = 0
