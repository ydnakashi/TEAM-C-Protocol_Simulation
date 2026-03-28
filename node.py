from dataclasses import dataclass
from enum import Enum, auto
import math
import sys

class NodeType(Enum):
    ASLEEP = -1
    AWAKE = 0
    BASE_STATION = 1
    CLUSTER_HEAD = 2
    SUBCLUSTER_HEAD = 3
    ORDINARY = 4
    IRRESOLUTE = 5
    DEAD = 6

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

class Energy(Enum): # All in joules
    ENERGY_PER_BIT = 50.0 # nj/bit
    EPSILON_FS = 10.0e-3   # nj/bit/m^2
    ENERGY_DA = 5.0 # nj/bit/signal
    EPSILON_AMP = 0.0013e-3 # nj/bit/m^4
    MAX_BATTERY = 0.5e9 # nj

class Action(Enum):
    SEND_DATA = "SEND_DATA"
    SEND_DATA_ACK = "SEND_DATA_ACK"
    WAITING_FOR_SEND_DATA_ACK = "WAITING_FOR_SEND_DATA_ACK"
    IDLE = "IDLE"
    ELECTION = "ELECTION"
    ORPHAN_ELECTION = "ORPHAN_ELECTION"
    AWAIT_REQS = "AWAIT_REQS"

def find_index_by_id(tuples_list, first_elem):
            for i, t in enumerate(tuples_list):
                if t[0].id == first_elem:
                    return i
            return -1

class Node:
    def __init__(self, id, powerPercent=100, coords=None, bsCoords = [0, 0], Rc=2): # power in nanojoules
        # What the node knows in reality
        self.id: int = id
        self.state: NodeType = NodeType.ASLEEP

        self.power: float = (Energy.MAX_BATTERY.value)*(powerPercent/100)
        self.powerPercent: float = powerPercent
        self.worthiness: float = 1
        self.overall_score: float = 1

        self.coords: tuple[int, int] = coords   # own coordinates
        self.bsCoords: tuple[int, int] = bsCoords  # base station coordinates

        self.chdList: dict[int, Child] = {}
        self.parent = Parent()

        self.twait = 0
        self.Rc = Rc

        self.action = Action.IDLE
        self.ready_to_send = True
        self.pkt = None
        self.timer = -1
        self.tdmaSlot = -1  # Default to -1 to represent no slot
        self.totalSlots = -1  # Default to -1 to represent no slot
        # self.waiting = 0
        self.orphan_timer = -1
        self.orphans = {}
        self.await_parent = False

        # For simulation purposes
        self.neighbourList: list[tuple[Node, float]] = []   # (node object, node distance from self) for all nodes of radius <= Rc
        self.broadcastList: list[tuple[Node, float]] = []   # (node object, node distance from self) for all nodes of radius <= 3/2*Rc
        self.relayList: list[tuple[Node, float]] = []       # (node object, node distance from self) for all nodes of radius <= 3*Rc
        self.label=f"Node {self.id}"

    def send_sensor_data(self):
        message = {
            "type": "SEND_DATA",
            "data": 100
        }
        self.send(message, self.parent.node, self.parent.distance)

    def select_state(self):
        if self.state == NodeType.BASE_STATION:
            return
        elif self.state == NodeType.AWAKE or self.state == NodeType.IRRESOLUTE:
            self.state = NodeType.CLUSTER_HEAD
            self.send_state_message()

    def send_state_message(self):
        msg = {
            "type": "STATE",
            "sender": self.id,
            "state": self.state,
            "coords": self.coords,
        }

        nodeList = []
        if self.state == NodeType.CLUSTER_HEAD:
            nodeList = [t[0] for t in self.neighbourList + self.broadcastList]
            self.consume_energy(sys.getsizeof(msg), 3/2*self.Rc)
        elif self.state == NodeType.SUBCLUSTER_HEAD:
            nodeList = [t[0] for t in self.neighbourList]
            self.consume_energy(sys.getsizeof(msg), self.Rc)
        else:
            return
        # don't use send function here since it issues one state message to a wide area
        for node in nodeList:
            node.receive(self, msg)

    def select_parent(self, baseStationNode: Node):
        if self.state == NodeType.BASE_STATION:
            return
        elif self.state == NodeType.CLUSTER_HEAD:
            self.parent.node = baseStationNode

            # Get list of nodes in relay and broadcast list that are clusterheads
            nodeList = [t[0] for t in self.relayList + self.broadcastList if t[0].state == NodeType.CLUSTER_HEAD]
        
            # If node list contains no nodes within range that are cluster heads, make base station the parent and return
            if not nodeList:
                return

            # Get list of nodes to distance to base station
            distanceList = [(node, math.sqrt((node.coords[0]-0)**2 + (node.coords[1]-0)**2)) for node in nodeList]
            
            # Get their self distance to base station
            BSdist = math.sqrt((self.coords[0]-self.bsCoords[0])**2 + (self.coords[1]-self.bsCoords[1])**2)

            # Get neighbour node closest to base station
            minNode, minDist = min(distanceList, key=lambda t: t[1])
            if minDist < BSdist:
                self.parent.node = minNode
        else:
            nodeList = self.neighbourList
            for neighbour, _ in sorted(nodeList, key=lambda t:t[1]):
                if (self.state == NodeType.ORDINARY and neighbour.state == NodeType.SUBCLUSTER_HEAD) \
                    or (self.state == NodeType.SUBCLUSTER_HEAD and neighbour.state == NodeType.CLUSTER_HEAD):
                    self.parent.node = neighbour
                    break
            if self.parent.node == None:
                raise ValueError(f"Parent selection error for Node {self.id}")
        self.send_memberjoin_message()
    
    def send_memberjoin_message(self):
        msg = {
            "type": "MEMBERJOIN",
            "id": self.id,
            "state": self.state,
            "coords": self.coords
        }
        self.send(msg, self.parent.node, self.parent.distance)

    def send(self, message: dict, recipient: Node, distance: float):
        self.consume_energy(sys.getsizeof(message), distance)
        recipient.receive(self, message)
    
    def broadcast(self, message):
        # get all nodes within the Rc distance
        if self.state == NodeType.CLUSTER_HEAD:
            self.consume_energy(sys.getsizeof(message), 3/2*self.Rc)
        else:
            self.consume_energy(sys.getsizeof(message), self.Rc)
        
        if(message['type'] == "STATE"):
            for neighbour, dist in self.neighbourList:
                neighbour.receive(self, message)
            if self.state == NodeType.CLUSTER_HEAD:
                for neighbour, dist in self.broadcastList:
                    neighbour.receive(self, message)
        elif (message['type'] == "POWERREQ"):
            if self.state == NodeType.DEAD:
                return
            print(self.chdList)
            for chd in self.chdList:
                self.chdList[chd].node.receive(self, message)

    def receive(self, sender: Node, message: dict):
        # helper function
        def float_node(tuples_list, nodeId):
            index = find_index_by_id(tuples_list, nodeId)
            if index == -1:
                raise ValueError("Node floating failed")
            tup = tuples_list.pop(index)
            tuples_list.insert(0, tup)

        # direct neighbour   
        if message["type"] == "STATE":
            if self.state == NodeType.ASLEEP: 
                self.state = NodeType.AWAKE

            senderId = message["sender"]
            if senderId in [t[0].id for t in self.neighbourList]:
                # float latest STATE message sender to top to make sure former IR nodes are selected for parent CH
                float_node(self.neighbourList, senderId)

                # State selection
                if self.state == NodeType.AWAKE:
                    if message['state'] == NodeType.CLUSTER_HEAD:
                        self.state = NodeType.SUBCLUSTER_HEAD
                        self.send_state_message()
                    elif message['state'] == NodeType.SUBCLUSTER_HEAD:
                        self.state = NodeType.ORDINARY

            elif senderId in [t[0].id for t in self.broadcastList]:
                # float latest STATE message sender to top to make sure former IR nodes are selected for parent CH
                float_node(self.broadcastList, senderId)

                # State selection
                if self.state == NodeType.AWAKE:
                    self.state = NodeType.IRRESOLUTE

        if message["type"] == "MEMBERJOIN":
            dist = math.sqrt((self.coords[0]-message['coords'][0])**2 + (self.coords[1]-message['coords'][1])**2)
            self.chdList[message['id']] = Child(
                state=message['state'], 
                node=sender,
                x=message['coords'][0],
                y=message['coords'][1],
                distance=dist)

        if message['type'] == "POWERREQ":
            if self.state == NodeType.DEAD:
                return

            self.parent.powerPercent = message['parentPower']

            sender.receive(self, message={
                "type": "POWERRETURN",
                "power": self.powerPercent
            })

        elif message['type'] == "POWERRETURN":
            if self.state == NodeType.DEAD:
                return
            self.chdList[sender.id].powerPercent = message["power"]
                
            
    def neighbourCount(self):
        return len(self.neighbourList)
    
    def childrenWaiting(self):
        waiting = [c for c in self.chdList.values() if not c.received]
        # print(self.id, " waiting ", waiting)
        return len(waiting)
    
    def resetWaiting(self):
        for c in self.chdList.values():
            c.received = False

    # icd used to calcualte twait time
    # euclidan distance of all the nodes in its neighbour array
    def calculateICD(self, distance_matrix):
        if not self.neighbourList:
            return 0

        total = 0
        for neighbour in self.neighbourList:
            total += distance_matrix[self.id][neighbour.id]

        return total / len(self.neighbourList)
    
    def consume_energy(self, k: int, d: float) -> None:
        consumption = 0.0
        if self.state == NodeType.BASE_STATION:
            consumption = 0
        elif self.state == NodeType.CLUSTER_HEAD:
            consumption = (len(self.chdList) + 1) * k * (Energy.ENERGY_PER_BIT.value + Energy.ENERGY_DA.value) + Energy.EPSILON_FS.value * k * d**2
        elif self.state == NodeType.SUBCLUSTER_HEAD:
            consumption = (len(self.chdList) + 1) * k * (Energy.ENERGY_PER_BIT.value + Energy.ENERGY_DA.value) + Energy.EPSILON_AMP.value * k * d**4
        else:
            consumption = Energy.ENERGY_PER_BIT.value * k + Energy.EPSILON_FS.value * k * d**2
        self.power -= consumption
        self.powerPercent = self.power/(0.5e9) *100
        if self.power < 0:
            self.power = 0
            self.powerPercent = 0
        print(f"{self.id}: {self.powerPercent}")

@dataclass
class Child:
    """A node that sends packets to its parent. Seen from the view of the parent."""
    # What the node wouldn't know in real life, used for simulation purposes
    node: Node
    
    # What the node should know
    state: NodeType
    tdma_slot: int = -1    # -1 means no slot given
    received: bool = False
    overall_score: float = 1
    L: int = 0
    N: int = 0
    powerPercent: float = 0.0
    x: int = 0
    y: int = 0
    distance: float = 0.0

@dataclass
class Parent:
    # What the node should not know, used for simulation
    node: Node = None

    # What the node should know about their parent
    L: int = 0
    N: int = 0
    overall_score: float = 1
    powerPercent: float = 0.0
    x: int = 0
    y: int = 0
    distance: float = 0.0
