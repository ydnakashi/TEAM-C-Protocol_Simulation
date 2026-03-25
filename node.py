from dataclasses import dataclass
from enum import Enum, auto
import math

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
    ENERGY_PER_BIT = 50
    ON_CONSUMPTION = auto()
    S_CH_CONSUMPTION = auto()
    CH_CONSUMPTION = auto()
    BASE_STATION_CONSUMPTION = auto()

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
    def __init__(self, id, power=100, coords=[0,0]):
        self.id = id
        self.state = None
        self.power = power
        self.coords = coords
        self.worthiness = 1
        self.overall_score = 100
        # self.timeSlot = 0
        self.currentBSDist = 1000000000

        self.chdList = {}
        self.neighbourList = []
        # twait is effected by neighbours within the RC, but broadcast messages can reach 3/2 x RC 
        self.broadcastList = []
        self.parent = Parent()

        self.twait = 0

        self.label=f"Node {self.id}"
      
        self.action = Action.IDLE
        self.ready_to_send = False
        self.pkt = None
        self.timer = -1
        self.tdmaSlot = -1  # Default to -1 to represent no slot
        self.totalSlots = -1  # Default to -1 to represent no slot
        self.waiting = 0

    def broadcast (self, message):
        # print(f"Node {self.id} received:", message)

        # get all nodes within the Rc distance
        if(message['type'] == "BROADCAST"):
            for neighbour, dist in self.neighbourList:
                neighbour.receive(self, message, 0)

            for neighbour, dist in self.broadcastList:
                neighbour.receive(self, message, 1)
        if(message['type'] == "MEMBERJOIN"):
            self.parent.node.receive(self, message, -1)

        if(message['type'] == "CHROUTE"):
            for neighbour, dist in self.neighbourList:
                neighbour.receive(self, message, -1)

    def receive(self, sender, message, neighbourType):
        # direct neighbour   
        if message["type"] == "BROADCAST" and neighbourType == 0:
            self.parent.node = sender
            # makes it a SubCH
            if message['state'] == NodeType.CLUSTER_HEAD:
                self.state = NodeType.SUBCLUSTER_HEAD
            else:
                # ordinary node
                self.state = NodeType.ORDINARY
        
         # in broadcast range, no parent
        if message["type"] == "BROADCAST" and neighbourType == 1 and self.state == None:
            # IR state
            self.parent.node = sender
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

        
    def addNeighbour(self, node):
        self.neighbourList.append(node)

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
        if self.nodeType == NodeType.ORDINARY:
            consumption = EnergyConsumption.ENERGY_PER_BIT * k + EnergyConsumption.EPSILON_FS * k * d^2
        elif self.nodeType == NodeType.BASE_STATION:
            consumption = 0
        else:
            if (d < EnergyConsumption.DISTANCE_LIMIT):
                consumption = (len(self.childList) + 1) * k * (EnergyConsumption.ENERGY_PER_BIT + EnergyConsumption.ENERGY_DA) + EnergyConsumption.EPSILON_FS * k * d^2
            else:
                consumption = (len(self.childList) + 1) * k * (EnergyConsumption.ENERGY_PER_BIT + EnergyConsumption.ENERGY_DA) + EnergyConsumption.EPSILON_AMP * k * d^4
        self.energy -= consumption

@dataclass
class Parent:
    node: Node = None
    L: int = 0
    N: int = 0
    overall_score: float = 0
