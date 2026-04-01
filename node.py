from dataclasses import dataclass
from enum import Enum
import math
import sys

CONSUMPTION_FACTOR = 1

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
    NodeType.ASLEEP:          ("#45475a", 0.55, 130),
    NodeType.IRRESOLUTE:      ("#fab387", 0.80, 200),
    NodeType.CLUSTER_HEAD:    ("#f38ba8", 1.00, 600),
    NodeType.SUBCLUSTER_HEAD: ("#cba6f7", 1.00, 380),
    NodeType.ORDINARY:        ("#89b4fa", 1.00, 260),
    NodeType.DEAD:            ("#1e1e2e", 0.65, 100),
}


class Energy(Enum):
    """All values in nanojoules."""
    ENERGY_PER_BIT = 50.0        # nJ/bit
    EPSILON_FS     = 10.0e-3     # nJ/bit/m^2
    ENERGY_DA      = 5.0         # nJ/bit/signal
    EPSILON_AMP    = 0.0013e-3   # nJ/bit/m^4
    MAX_BATTERY    = 0.5e9       # nJ


class Action(Enum):
    SEND_DATA = "SEND_DATA"
    SEND_DATA_ACK = "SEND_DATA_ACK"
    WAITING_FOR_SEND_DATA_ACK = "WAITING_FOR_SEND_DATA_ACK"
    IDLE = "IDLE"
    ELECTION = "ELECTION"
    ORPHAN_ELECTION = "ORPHAN_ELECTION"
    AWAIT_REQS = "AWAIT_REQS"


def _find_index_by_id(tuples_list, node_id):
    """Return the index of the tuple whose first element has the given id, or -1."""
    for i, t in enumerate(tuples_list):
        if t[0].id == node_id:
            return i
    return -1


def _float_node_to_front(tuples_list, node_id):
    """Move the entry matching node_id to the front of the list (for priority during parent selection)."""
    index = _find_index_by_id(tuples_list, node_id)
    if index == -1:
        raise ValueError(f"Node {node_id} not found in list")
    tup = tuples_list.pop(index)
    tuples_list.insert(0, tup)


class Node:
    def __init__(self, id, powerPercent=100, coords=None, bsCoords=None, Rc=2):
        if bsCoords is None:
            bsCoords = [0, 0]

        # Identity
        self.id: int = id
        self.state: NodeType = NodeType.ASLEEP
        self.label = f"Node {self.id}"

        # Energy
        self.power: float = Energy.MAX_BATTERY.value * (powerPercent / 100)
        self.powerPercent: float = powerPercent

        # Scoring (used during elections)
        self.overall_score: float = 1

        # Position
        self.coords: tuple[int, int] = coords
        self.bsCoords: tuple[int, int] = bsCoords

        # Cluster relationships
        self.chdList: dict[int, Child] = {}
        self.parent = Parent()

        # Timing
        self.twait = 0
        self.Rc = Rc
        self.timer = -1
        self.tdmaSlot = -1
        self.totalSlots = -1
        self.orphan_timer = -1

        # State machine
        self.action = Action.IDLE
        self.pkt = None
        self.orphans = {}
        self.await_parent = False

        # Simulation-only: neighbour lists at increasing radii
        self.neighbourList: list[tuple[Node, float]] = []   # radius <= Rc
        self.broadcastList: list[tuple[Node, float]] = []   # Rc < radius <= 1.5*Rc
        self.relayList: list[tuple[Node, float]] = []       # 1.5*Rc < radius <= 3*Rc

    # ── State Selection (clustering phase) ──────────────

    def select_state(self):
        if self.state == NodeType.BASE_STATION:
            return
        if self.state in (NodeType.AWAKE, NodeType.IRRESOLUTE):
            self.state = NodeType.CLUSTER_HEAD
            self._broadcast_state()

    def _broadcast_state(self):
        """Broadcast this node's state to neighbours (and broadcast-range nodes if CH)."""
        msg = {
            "type": "STATE",
            "sender": self.id,
            "state": self.state,
            "coords": self.coords,
        }

        if self.state == NodeType.CLUSTER_HEAD:
            recipients = [t[0] for t in self.neighbourList + self.broadcastList]
            self.consume_energy(sys.getsizeof(msg), 1.5 * self.Rc)
        elif self.state == NodeType.SUBCLUSTER_HEAD:
            recipients = [t[0] for t in self.neighbourList]
            self.consume_energy(sys.getsizeof(msg), self.Rc)
        else:
            return

        for node in recipients:
            node.receive(self, msg)

    # ── Parent Selection (cluster formation) ────────────

    def select_parent(self, base_station_node):
        if self.state == NodeType.BASE_STATION:
            return

        if self.state == NodeType.CLUSTER_HEAD:
            self._select_parent_as_ch(base_station_node)
        else:
            self._select_parent_as_member()

        self._send_memberjoin()

    def _select_parent_as_ch(self, base_station_node):
        """CH selects the closest-to-BS cluster head as relay parent, or defaults to BS."""
        self.parent.node = base_station_node

        candidates = [t[0] for t in self.broadcastList + self.relayList
                       if t[0].state == NodeType.CLUSTER_HEAD]
        if not candidates:
            return

        def dist_to_bs(node):
            return math.sqrt((node.coords[0] - node.bsCoords[0])**2 +
                             (node.coords[1] - node.bsCoords[1])**2)

        self_bs_dist = dist_to_bs(self)
        closest_node = min(candidates, key=dist_to_bs)
        if dist_to_bs(closest_node) < self_bs_dist:
            self.parent = Parent(node=closest_node)

    def _select_parent_as_member(self):
        """Sub-CH or ordinary node selects the closest appropriate parent from neighbours."""
        expected_parent_state = {
            NodeType.ORDINARY: NodeType.SUBCLUSTER_HEAD,
            NodeType.SUBCLUSTER_HEAD: NodeType.CLUSTER_HEAD,
        }.get(self.state)

        for neighbour, _ in sorted(self.neighbourList, key=lambda t: t[1]):
            if neighbour.state == expected_parent_state:
                self.parent = Parent(node=neighbour)
                return

        raise ValueError(f"Parent selection error for Node {self.id}")

    def _send_memberjoin(self):
        msg = {
            "type": "MEMBERJOIN",
            "id": self.id,
            "state": self.state,
            "coords": self.coords,
        }
        self.send(msg, self.parent.node, self.parent.distance)

    # ── Messaging ───────────────────────────────────────

    def send(self, message: dict, recipient, distance: float):
        self.consume_energy(sys.getsizeof(message), distance)
        recipient.receive(self, message)

    def broadcast(self, message):
        if self.state == NodeType.CLUSTER_HEAD:
            self.consume_energy(sys.getsizeof(message), 1.5 * self.Rc)
        else:
            self.consume_energy(sys.getsizeof(message), self.Rc)

        if message['type'] == "STATE":
            for neighbour, _ in self.neighbourList:
                neighbour.receive(self, message)
            if self.state == NodeType.CLUSTER_HEAD:
                for neighbour, _ in self.broadcastList:
                    neighbour.receive(self, message)

        elif message['type'] == "POWERREQ":
            if self.state == NodeType.DEAD:
                return
            for _, chd in self.chdList.items():
                chd.node.receive(self, message)
                self.consume_energy(sys.getsizeof(message), chd.distance)

    def receive(self, sender, message):
        msg_type = message["type"]

        if msg_type == "STATE":
            self._handle_state_msg(message)
        elif msg_type == "MEMBERJOIN":
            self._handle_memberjoin(sender, message)
        elif msg_type == "POWERREQ":
            self._handle_power_req(sender, message)
        elif msg_type == "POWERRETURN":
            self._handle_power_return(sender, message)
        elif msg_type == "UPDATESCORE":
            self._handle_update_score(message)

    def _handle_state_msg(self, message):
        if self.state == NodeType.ASLEEP:
            self.state = NodeType.AWAKE

        sender_id = message["sender"]

        # Check if sender is a direct neighbour
        if sender_id in [t[0].id for t in self.neighbourList]:
            _float_node_to_front(self.neighbourList, sender_id)
            if self.state == NodeType.AWAKE:
                if message['state'] == NodeType.CLUSTER_HEAD:
                    self.state = NodeType.SUBCLUSTER_HEAD
                    self._broadcast_state()
                elif message['state'] == NodeType.SUBCLUSTER_HEAD:
                    self.state = NodeType.ORDINARY

        # Check if sender is in broadcast range
        elif sender_id in [t[0].id for t in self.broadcastList]:
            _float_node_to_front(self.broadcastList, sender_id)
            if self.state == NodeType.AWAKE:
                self.state = NodeType.IRRESOLUTE

    def _handle_memberjoin(self, sender, message):
        dist = math.sqrt((self.coords[0] - message['coords'][0])**2 +
                         (self.coords[1] - message['coords'][1])**2)
        self.chdList[message['id']] = Child(
            state=message['state'],
            node=sender,
            x=message['coords'][0],
            y=message['coords'][1],
            distance=dist,
        )

    def _handle_power_req(self, sender, message):
        if self.state == NodeType.DEAD:
            return
        self.parent.powerPercent = message['parentPower']
        sender.receive(self, {"type": "POWERRETURN", "power": self.powerPercent})

    def _handle_power_return(self, sender, message):
        if sender.id in self.chdList:
            self.chdList[sender.id].powerPercent = message["power"]

    def _handle_update_score(self, message):
        if self.state == NodeType.DEAD or self.power <= 0:
            return
        self.overall_score = message['childworth']

    # ── TDMA helpers ────────────────────────────────────

    def children_waiting(self):
        return sum(1 for c in self.chdList.values() if not c.received)

    def reset_waiting(self):
        for c in self.chdList.values():
            c.received = False

    # ── Energy ──────────────────────────────────────────

    def consume_energy(self, k: int, d: float) -> None:
        if self.state == NodeType.BASE_STATION:
            return

        if self.state == NodeType.CLUSTER_HEAD:
            consumption = ((len(self.chdList) + 1) * k *
                           (Energy.ENERGY_PER_BIT.value + Energy.ENERGY_DA.value) +
                           Energy.EPSILON_FS.value * k * d**2)
        elif self.state == NodeType.SUBCLUSTER_HEAD:
            consumption = ((len(self.chdList) + 1) * k *
                           (Energy.ENERGY_PER_BIT.value + Energy.ENERGY_DA.value) +
                           Energy.EPSILON_AMP.value * k * d**4)
        else:
            consumption = (Energy.ENERGY_PER_BIT.value * k +
                           Energy.EPSILON_FS.value * k * d**2)

        self.power -= CONSUMPTION_FACTOR * consumption
        if self.power <= 0:
            self.power = 0
            self.powerPercent = 0
            self.state = NodeType.DEAD
        else:
            self.powerPercent = self.power / Energy.MAX_BATTERY.value * 100


# ── Data classes ────────────────────────────────────────

@dataclass
class Child:
    """A child node as seen by its parent."""
    node: Node                     # simulation reference
    state: NodeType
    tdma_slot: int = -1
    received: bool = False
    overall_score: float = 1
    L: int = 0                     # packets successfully delivered
    N: int = 0                     # packets expected
    powerPercent: float = 0.0
    x: int = 0
    y: int = 0
    distance: float = 0.0


@dataclass
class Parent:
    """A parent node as seen by its child."""
    node: Node = None              # simulation reference
    L: int = 0
    N: int = 0
    overall_score: float = 1
    worthiness_score: float = 1
    powerPercent: float = 0.0
    x: int = 0
    y: int = 0
    distance: float = 0.0
