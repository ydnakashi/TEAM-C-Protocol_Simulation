"""
network_model.py — Model Layer

Wireless sensor network simulation supporting MI2RSDiC and TEAM-C protocols.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import networkx as nx

from node import Child, Node, NodeType, Parent, Action


# ──────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────

@dataclass
class NetworkStats:
    """Snapshot of high-level network metrics."""
    num_nodes: int
    num_edges: int
    is_connected: bool
    num_components: int
    edges: list[tuple[int, int, dict]]


@dataclass
class LayoutResult:
    """Node positions + formatted edge labels, ready for any renderer."""
    positions: dict[int, tuple[float, float]]
    node_labels: dict[int, str]
    edge_labels: dict[tuple[int, int], str]


class PacketStatus(Enum):
    IN_TRANSIT = auto()
    DELIVERED  = auto()
    DROPPED    = auto()


class Phase(Enum):
    INIT_ROLES = auto()
    ROUTING = auto()
    ELECTION = auto()


@dataclass
class Packet:
    """A single data packet traversing the network."""
    packet_id: int
    source: int
    destination: int
    path: list[int]
    content: dict
    hop_index: int = 0
    progress: float = 0.0
    status: PacketStatus = PacketStatus.IN_TRANSIT

    @property
    def current_node(self) -> int:
        return self.path[self.hop_index]

    @property
    def next_node(self) -> int | None:
        if self.hop_index + 1 < len(self.path):
            return self.path[self.hop_index + 1]
        return None

    @property
    def is_delivered(self) -> bool:
        return self.status == PacketStatus.DELIVERED


@dataclass
class SimulationSnapshot:
    """Everything the View needs to render one frame."""
    tick: int
    packets: list[Packet]
    base_station: int
    delivered_count: int
    dropped_count: int
    active_count: int
    events: list[str]
    dead: bool


class Protocol(Enum):
    MI2RSDiC = auto()
    TEAM_C = auto()


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _randomize_battery(seed):
    """Seeded random battery level between 45-100%."""
    random.seed(seed)
    return float(random.randint(45, 100))


def _dist(a, b):
    """Euclidean distance between two nodes."""
    x1, y1 = a.coords
    x2, y2 = b.coords
    return ((x1 - x2)**2 + (y1 - y2)**2) ** 0.5


# ──────────────────────────────────────────────
#  The Model
# ──────────────────────────────────────────────

class NetworkModel:
    """
    Wireless network graph + discrete-tick packet simulation.
    Every public method is a pure network / simulation operation.
    """

    def __init__(self) -> None:
        self._graph: nx.Graph = nx.Graph()

        # Simulation state
        self._base_station: int = 1
        self._packets: list[Packet] = []
        self._next_packet_id: int = 1
        self._tick: int = 0
        self._delivered: int = 0
        self._dropped: int = 0
        self._spawn_interval: int = 6
        self._events: list[str] = []
        self._tdma_slot: int = 0
        self._phase: Phase = Phase.INIT_ROLES
        self._loss_interval: int = 3

        # Node destruction
        self._destroyed_prob: dict[int, int] = {}
        self._destroyed: set[int] = set()
        self._to_remove: set[int] = set()
        self._nodes_to_destroy: list[int] = [9, 2]

        # Statistics
        self._received_packets_at_BS: int = 0
        self._throughputs: list[int] = []
        self._delivered_interval: int = 0

        # Protocol selection
        self._protocol: Protocol = Protocol.TEAM_C

    # ── Properties ───────────────────────────

    @property
    def graph(self) -> nx.Graph:
        return self._graph

    @property
    def base_station(self) -> int:
        return self._base_station

    # ══════════════════════════════════════════
    #  Graph building / mutation
    # ══════════════════════════════════════════

    def build_from_matrix(self, matrix: list[list[float]]) -> None:
        self._graph.clear()
        n = len(matrix)
        for i in range(n):
            self._graph.add_node(i + 1, label=f"Node {i + 1}")
        for i in range(n):
            for j in range(i + 1, n):
                dist = matrix[i][j]
                if dist > 0:
                    self._graph.add_edge(i + 1, j + 1, weight=dist)

    def build_from_coordinates(self, coords: list[tuple[float, float]], link_range: float = 2.0) -> None:
        """Create graph from list of coordinates input by user"""
        self._graph.clear()
        n = len(coords)

        # Fixed battery overrides for specific nodes (demo/testing)
        battery_overrides = {6: 65, 7: 98, 11: 75}

        for i in range(n):
            node_id = i + 1
            battery = battery_overrides.get(node_id, _randomize_battery(node_id))
            self._graph.add_node(
                node_id,
                label=f"Node{node_id}",
                node=Node(id=node_id, powerPercent=battery,
                          coords=[coords[i][0], coords[i][1]], Rc=link_range),
            )

        for i in range(n):
            for j in range(i + 1, n):
                x0, y0 = coords[i]
                x1, y1 = coords[j]
                dist = ((x1 - x0)**2 + (y1 - y0)**2) ** 0.5
                if 0 < dist <= link_range:
                    self._graph.add_edge(i + 1, j + 1, weight=round(dist, 2))

    def compute_layout_from_coords(self, coords: list[tuple[float, float]]) -> LayoutResult:
        """Build a LayoutResult using provided (x, y) coordinates as node positions."""
        G = self._graph
        positions = {i + 1: coords[i] for i in range(len(coords))}
        node_labels = {nd: f"N{nd}" for nd in G.nodes()}
        raw = nx.get_edge_attributes(G, "weight")
        edge_labels = {k: f"{v:.2f} m" for k, v in raw.items()}
        return LayoutResult(positions=positions, node_labels=node_labels,
                            edge_labels=edge_labels)

    def add_node(self, node_id: int, **attrs: Any) -> None:
        self._graph.add_node(node_id, **attrs)

    def remove_node(self, node_id: int) -> None:
        self._graph.remove_node(node_id)

    def add_edge(self, u: int, v: int, weight: float) -> None:
        self._graph.add_edge(u, v, weight=weight)

    def remove_edge(self, u: int, v: int) -> None:
        self._graph.remove_edge(u, v)

    # ══════════════════════════════════════════
    #  Graph queries
    # ══════════════════════════════════════════

    def get_stats(self) -> NetworkStats:
        """Get information to display on th simulation"""
        G = self._graph
        has_nodes = G.number_of_nodes() > 0
        return NetworkStats(
            num_nodes=G.number_of_nodes(),
            num_edges=G.number_of_edges(),
            is_connected=nx.is_connected(G) if has_nodes else False,
            num_components=nx.number_connected_components(G) if has_nodes else 0,
            edges=list(G.edges(data=True)),
        )

    def has_edges(self) -> bool:
        return self._graph.number_of_edges() > 0

    def get_nodes(self) -> list[int]:
        return sorted(self._graph.nodes())

    def compute_layout(self, seed: int = 42) -> LayoutResult:
        G = self._graph
        n = G.number_of_nodes()
        positions = nx.spring_layout(G, seed=seed, k=2.5 / (n ** 0.5))
        node_labels = {nd: f"N{nd}" for nd in G.nodes()}
        raw = nx.get_edge_attributes(G, "weight")
        edge_labels = {k: f"{v:.0f} m" for k, v in raw.items()}
        return LayoutResult(positions=positions, node_labels=node_labels,
                            edge_labels=edge_labels)

    # ══════════════════════════════════════════
    #  Simulation setup
    # ══════════════════════════════════════════

    def set_base_station(self, node_id: int) -> None:
        """Initialize base station"""
        if node_id not in self._graph.nodes():
            raise ValueError(f"Node {node_id} not in graph")
        self._base_station = node_id
        self._graph.nodes[node_id]["node"].state = NodeType.BASE_STATION

    def reset_simulation(self) -> None:
        """Clear all packets and counters; keep graph + base station."""
        self._packets.clear()
        self._next_packet_id = 1
        self._tick = 0
        self._delivered = 0
        self._dropped = 0
        self._events.clear()

    def _get_node(self, ni: int) -> Node:
        """Shorthand to retrieve the Node object for graph node ni."""
        return self._graph.nodes[ni]["node"]

    def get_source_nodes(self) -> list[int]:
        """Non-base nodes that have a path to the base station."""
        return sorted(
            nd for nd in self._graph.nodes()
            if nd != self._base_station and nx.has_path(self._graph, nd, self._base_station)
        )

    def get_parent_nodes(self) -> list[int]:
        """Nodes that have children."""
        return sorted(
            nd for nd in self._graph.nodes()
            if len(self._get_node(nd).chdList) > 0
        )

    def init_actions(self):
        """Leaf nodes (no children) start by sending data."""
        for ni in self._graph.nodes():
            if len(self._get_node(ni).chdList) == 0:
                self._get_node(ni).action = Action.SEND_DATA

    # ══════════════════════════════════════════
    #  TDMA scheduling
    # ══════════════════════════════════════════

    def create_TDMA_schedule(self, ni):
        """Create TDMA schedule for node's children."""
        node = self._get_node(ni)
        total = len(node.chdList)

        for slot, (child_id, child) in enumerate(node.chdList.items()):
            self._get_node(child_id).tdmaSlot = slot
            child.tdma_slot = slot

        node.reset_waiting()
        node.timer = -1

        for child_id in node.chdList:
            self._get_node(child_id).totalSlots = total

    def spawn_TDMA_packets(self, parent_id, ready=True):
        """Spawn MEMBERACK packets to inform children of their TDMA schedule."""
        parent_node = self._get_node(parent_id)
        schedule = {cid: c.tdma_slot for cid, c in parent_node.chdList.items()}
        for child_id in parent_node.chdList:
            msg = {
                "schd": schedule,
                "tt": len(parent_node.chdList),
                "ready": ready,
                "type": "MEMBERACK",
            }
            self.spawn_packet(msg, parent_id, child_id)

    def update_TDMA_slot(self, node_id: int, slot: int, total_slots: int):
        """Record TDMA schedule information when received by a node."""
        node = self._get_node(node_id)
        node.tdmaSlot = slot
        node.totalSlots = total_slots

    def init_TDMA(self):
        for parent_id in self.get_parent_nodes():
            self.create_TDMA_schedule(parent_id)
            self.spawn_TDMA_packets(parent_id)

    # ══════════════════════════════════════════
    #  Worthiness scoring
    # ══════════════════════════════════════════

    def calculate_worthiness_score(self, L, N, c=1):
        """
        Compute worthiness from packet delivery ratio (L/N) and statistical dispersion.
        Returns 0 if no packets expected, 1 if more delivered than expected.
        """
        if N == 0:
            return 0
        if L > N:
            return 1
        t = L / N
        r = 1 - (((12 * L * (N - L))**0.5) / ((N + 1) * N))
        w = 1 - (((t - 1)**2 + (c**2) * (r - 1)**2)**0.5 / (1 + c**2)**0.5)
        return w

    def start_worthiness_calc(self):
        """Recalculate worthiness scores for all active nodes' parents and children."""
        for ni in self._graph.nodes:
            if ni in self._destroyed or ni in self._to_remove:
                continue
            node = self._get_node(ni)

            # Protocol weights: MI2RSDiC uses battery only, TEAM-C uses 50/50
            if self._protocol == Protocol.MI2RSDiC:
                w_weight, p_weight = 0, 1
            else:
                w_weight, p_weight = 0.5, 0.5

            # Parent score
            parent_worthiness = self.calculate_worthiness_score(node.parent.L, node.parent.N)
            node.parent.overall_score = (w_weight * parent_worthiness +
                                          p_weight * (node.parent.powerPercent / 100))
            node.parent.worthiness_score = parent_worthiness
            node.parent.L = 0
            node.parent.N = 0

            # Children scores
            for _, child_obj in node.chdList.items():
                child_worthiness = self.calculate_worthiness_score(child_obj.L, child_obj.N)
                child_obj.overall_score = (0.5 * child_worthiness +
                                            0.5 * (child_obj.powerPercent / 100))
                child_obj.N = 0
                child_obj.L = 0

    # ══════════════════════════════════════════
    #  Node destruction
    # ══════════════════════════════════════════

    def cleanup_dead_nodes(self):
        for ni in self._graph.nodes:
            node = self._get_node(ni)
            if node.id in self._to_remove:
                self._destroyed.add(node.id)
                if node.parent is not None:
                    node.parent.node.chdList.pop(node.id, None)
        self._to_remove.clear()
        self._rebuild_edges()

    def init_destruction_probabilities(self, max_prob=40):
        """Initialize destruction probabilities (0 to max_prob) for each non-BS node."""
        random.seed(42)
        for ni in self.get_source_nodes():
            self._destroyed_prob[ni] = random.randrange(0, max_prob)

    def destroy_nodes(self):
        """Randomly destroy one node based on stored probabilities (max 5 destroyed)."""
        if len(self._destroyed) > 4:
            return
        for ni, prob in self._destroyed_prob.items():
            if random.randrange(0, 100) < prob and ni not in self._destroyed:
                self._destroy_node(ni)
                self._events.append(f"Destroyed node: {ni}")
                return

    def target_destroy(self):
        """Destroy the next node in the predetermined destruction queue."""
        if not self._nodes_to_destroy:
            return
        node_id = self._nodes_to_destroy.pop(0)
        self._destroy_node(node_id)

    def _destroy_node(self, node_id: int):
        """Mark a node as dead and remove it from its parent's child list."""
        self._destroyed.add(node_id)
        node = self._get_node(node_id)
        node.timer = -1
        node.powerPercent = 0
        node.state = NodeType.DEAD
        if node.parent.node is not None:
            node.parent.node.chdList.pop(node.id, None)
        self._rebuild_edges()

    # ══════════════════════════════════════════
    #  Edge management
    # ══════════════════════════════════════════

    def _rebuild_edges(self):
        """Rebuild graph edges from the current parent-child relationships."""
        self._graph.clear_edges()
        for ni in self._graph.nodes:
            node = self._get_node(ni)
            if node.id in self._destroyed:
                continue
            for child_id in node.chdList:
                self._graph.add_edge(node.id, child_id)

    # ══════════════════════════════════════════
    #  Packet management
    # ══════════════════════════════════════════

    def spawn_packet(self, content: dict, source: int, dest: int) -> Packet:
        """Create and send a packet from source to dest."""
        pkt = Packet(
            packet_id=self._next_packet_id,
            source=source,
            destination=dest,
            path=[source, dest],
            content=content,
        )
        self._next_packet_id += 1
        self._packets.append(pkt)

        route_str = " -> ".join(str(n) for n in pkt.path)
        self._events.append(
            f"[Tick {self._tick:>4}]  PKT #{pkt.packet_id:>3} {pkt.content['type']} "
            f"spawned at Node {pkt.source}   route: {route_str}"
        )

        source_node = self._get_node(source)
        dest_node = self._get_node(dest)
        source_node.send(content, dest_node, _dist(source_node, dest_node))
        return pkt

    def move_packets(self):
        """Advance all in-transit packets and handle delivery."""
        SPEED = 0.10

        for pkt in self._packets:
            if pkt.status != PacketStatus.IN_TRANSIT:
                continue

            pkt.progress += SPEED

            while pkt.progress >= 1.0 and pkt.status == PacketStatus.IN_TRANSIT:
                pkt.progress -= 1.0
                pkt.hop_index += 1

                if pkt.hop_index >= len(pkt.path) - 1:
                    self._deliver_packet(pkt)

    def _deliver_packet(self, pkt: Packet):
        """Handle a packet arriving at its destination."""
        if pkt.status != PacketStatus.DROPPED:
            pkt.hop_index = len(pkt.path) - 1
            pkt.progress = 0.0
            pkt.status = PacketStatus.DELIVERED
            self._delivered += 1
            self._delivered_interval += 1
            self._events.append(
                f"[Tick {self._tick:>4}]  PKT #{pkt.packet_id:>3} "
                f"DELIVERED -> Node {pkt.destination}"
            )

        if pkt.destination in self._destroyed:
            return

        node = self._get_node(pkt.destination)
        msg_type = pkt.content["type"]

        if msg_type == "DATA_MSG":
            self._handle_data_msg(node, pkt)
        elif msg_type == "MEMBERACK":
            self._handle_memberack(node, pkt)
        elif msg_type == "DATA_ACK":
            self._handle_data_ack(node, pkt)
        elif msg_type == "UPDATE_HEAD":
            self.update_new_head(pkt.destination, pkt.content)
            self._rebuild_edges()
        elif msg_type == "UPDATE_NOHEAD":
            self.update_no_head(pkt.destination, pkt.content)
            self._rebuild_edges()
        elif msg_type == "UPDATE_HEAD_ORPHAN":
            self.update_new_head_orphan(pkt.destination, pkt.content)
            self._rebuild_edges()
        elif msg_type == "READY":
            self._handle_ready(node, pkt)
        elif msg_type == "REQUEST_PARENT":
            self._handle_request_parent(node, pkt)

    def _handle_data_msg(self, node: Node, pkt: Packet):
        if pkt.source not in node.chdList:
            return
        node.chdList[pkt.source].powerPercent = pkt.content["power"]
        node.pkt = pkt
        if pkt.destination == self._base_station:
            self._received_packets_at_BS += 1

    def _handle_memberack(self, node: Node, pkt: Packet):
        if pkt.source != node.parent.node.id:
            return
        self.update_TDMA_slot(pkt.destination, pkt.content["schd"][pkt.destination], pkt.content["tt"])
        if len(node.chdList) == 0 and node.action in (Action.ELECTION, Action.IDLE):
            node.action = Action.SEND_DATA
        elif node.action == Action.ORPHAN_ELECTION:
            node.action = Action.ELECTION
        node.await_parent = False

    def _handle_data_ack(self, node: Node, pkt: Packet):
        if node.parent is None:
            pkt.status = PacketStatus.DROPPED
            return
        if self._protocol == Protocol.MI2RSDiC:
            node.action = Action.ELECTION
        elif not node.await_parent and node.action != Action.AWAIT_REQS:
            node.action = Action.ORPHAN_ELECTION
        node.parent.L += 1
        node.parent.powerPercent = pkt.content["power"]
        node.overall_score = pkt.content["overall_score"]
        node.ready_to_send = True

    def _handle_ready(self, node: Node, pkt: Packet):
        if pkt.source != node.parent.node.id:
            return
        if len(node.chdList) == 0 and node.action in (Action.ELECTION, Action.IDLE):
            node.action = Action.SEND_DATA
        elif node.action == Action.ORPHAN_ELECTION:
            node.action = Action.ELECTION
        node.ready_to_send = True

    def _handle_request_parent(self, node: Node, pkt: Packet):
        if node.orphan_timer == -1:
            node.orphan_timer = self._loss_interval
        orphan_node = self._get_node(pkt.source)
        node.orphans[pkt.source] = Child(
            orphan_node, orphan_node.state,
            overall_score=orphan_node.overall_score,
        )
        node.action = Action.AWAIT_REQS

    # ══════════════════════════════════════════
    #  Data transmission
    # ══════════════════════════════════════════

    def send_data_packet(self, ni):
        node = self._get_node(ni)

        if node.parent is None or ni not in node.parent.node.chdList:
            return

        # Parent tracks expected packets from this child
        node.parent.node.chdList[ni].N += 1

        if ni in self._destroyed:
            return

        node.parent.N += 1
        msg = {"power": node.powerPercent, "type": "DATA_MSG"}
        self.spawn_packet(msg, ni, node.parent.node.id)

        node.action = Action.IDLE
        node.orphan_timer = -1
        node.orphans = {}
        node.reset_waiting()
        node.timer = self._loss_interval * len(node.chdList)
        node.ready_to_send = False

    def send_data_ack(self, pkt):
        """Send acknowledgement back to the child that sent data."""
        node = self._get_node(pkt.destination)
        if pkt.source not in node.chdList:
            node.action = Action.IDLE
            return

        if node.timer <= -1:
            node.timer = self._loss_interval * len(node.chdList)

        self.spawn_packet({
            "power": node.powerPercent,
            "overall_score": node.chdList[pkt.source].overall_score,
            "type": "DATA_ACK",
        }, pkt.destination, pkt.source)

        node.chdList[pkt.source].L += 1
        node.pkt = None
        node.chdList[pkt.source].received = True

        if node.action == Action.IDLE:
            node.action = Action.SEND_DATA

    def send_election_msg(self, ni, msg):
        """Send message to children and parent if applicable to trigger a re-election"""
        if(msg["type"] == "UPDATE_HEAD"):
        if msg["type"] == "UPDATE_HEAD":
            self.spawn_packet(msg, ni, msg["oldParent"])
        elif msg["type"] == "UPDATE_NOHEAD":
            self.spawn_packet(msg, ni, msg["newHead"])
        for ci in msg["chdList"]:
            self.spawn_packet(msg, ni, ci)

    def send_ready_msg(self, ni):
        msg = {"type": "READY"}
        for ci in self._get_node(ni).chdList:
            self.spawn_packet(msg, ni, ci)

    # ══════════════════════════════════════════
    #  Main simulation tick
    # ══════════════════════════════════════════

    def tick(self) -> SimulationSnapshot:
        """
        Advance one discrete time step:
          1. On spawn interval: run clustering init or TDMA routing
          2. Periodically destroy nodes and recalculate worthiness
          3. Move packets forward and deliver
        """
        self._tick += 1
        self._events = []
        dead = False

        if self._tick % self._spawn_interval == 0:
            if self._phase == Phase.INIT_ROLES:
                self._run_init_phase()
            else:
                self._run_routing_phase()

        # Periodic node destruction
        if self._tick % 150 == 0:
            self.target_destroy()

        # Periodic worthiness recalculation and statistics
        if self._tick % 200 == 0:
            self.start_worthiness_calc()
            self.throughput()
            dead = self.network_dead()
            self._delivered_interval = 0

        self.move_packets()
        self.purge_delivered()
        active = [p for p in self._packets if p.status == PacketStatus.IN_TRANSIT]

        return SimulationSnapshot(
            tick=self._tick,
            packets=list(self._packets),
            base_station=self._base_station,
            delivered_count=self._delivered,
            dropped_count=self._dropped,
            active_count=len(active),
            events=list(self._events),
            dead=dead,
        )

    def _run_init_phase(self):
        """First tick: compute twait, assign roles, form clusters, start TDMA."""
        self._compute_twait()
        self._select_states()
        self._create_clusters()
        self.init_TDMA()
        self._rebuild_edges()
        self.init_destruction_probabilities()
        self.init_actions()
        self._phase = Phase.ROUTING

    def _run_routing_phase(self):
        """Each subsequent spawn-interval tick: advance TDMA slot and process node actions."""
        self._tdma_slot += 1

        for ni in self._graph.nodes():
            node = self._get_node(ni)
            node.timer -= 1

            if node.state == NodeType.DEAD:
                continue

            # TEAM-C: check if parent is still viable
            orphan_msg = None
            new_head_orphan = None
            if (self._protocol == Protocol.TEAM_C and
                    not node.await_parent and node.action != Action.AWAIT_REQS):
                orphan_msg, new_head_orphan = self.observe_parent_potential(ni, 0)
                if orphan_msg is not None:
                    node.action = Action.ORPHAN_ELECTION
                    node.await_parent = True

            # Action dispatch
            if self._should_send_data(ni, node):
                self.send_data_packet(ni)

            elif node.pkt:
                self.send_data_ack(node.pkt)

            elif self._should_run_election(node):
                self._process_election(ni, node)

            elif node.action == Action.ORPHAN_ELECTION:
                if orphan_msg is not None:
                    self.spawn_packet(orphan_msg, ni, new_head_orphan.id)
                else:
                    node.action = Action.ELECTION

            elif node.action == Action.AWAIT_REQS:
                self._process_orphan_requests(ni, node)

    def _should_send_data(self, ni, node) -> bool:
        return (ni != self._base_station and
                node.action == Action.SEND_DATA and
                self._tdma_slot % node.totalSlots == node.tdmaSlot and
                (node.children_waiting() == 0 or node.timer <= 0) and
                not node.await_parent)

    def _should_run_election(self, node) -> bool:
        return (node.action == Action.ELECTION and
                self._tdma_slot % node.totalSlots == node.tdmaSlot)

    def _process_election(self, ni, node):
        """Handle the election phase for a node."""
        node.action = Action.SEND_DATA

        if len(node.chdList) == 0:
            return

        msg = self.elect_new_head(ni, 0.7)
        if msg is None:
            self.send_ready_msg(ni)
            node.action = Action.IDLE
        else:
            self.send_election_msg(ni, msg)

    def _process_orphan_requests(self, ni, node):
        """Handle accumulated orphan requests after timer expires."""
        if node.orphan_timer != -1:
            node.orphan_timer -= 1
        if node.orphan_timer == 0:
            orph_msg = {"chdList": node.orphans}
            msg = self.elect_new_head_orphans(ni, orph_msg, 0.5)
            if msg is None:
                self.send_ready_msg(ni)
                self._rebuild_edges()
            else:
                self.send_election_msg(ni, msg)
            node.action = Action.ELECTION

    # ══════════════════════════════════════════
    #  Clustering initialization
    # ══════════════════════════════════════════

    def _compute_twait(self, graph_x=10, graph_y=10, Rc=2, alpha=0.5):
        """Compute twait values for all nodes based on neighbour density and ICD."""
        N = self._graph.number_of_nodes()

        # Build neighbour/broadcast/relay lists
        for ni in self._graph.nodes():
            node = self._get_node(ni)
            for oi in self._graph.nodes():
                other = self._get_node(oi)
                if node == other:
                    continue
                d = _dist(node, other)
                if d <= Rc:
                    node.neighbourList.append((other, d))
                elif d <= 1.5 * Rc:
                    node.broadcastList.append((other, d))
                elif d <= 3 * Rc:
                    node.relayList.append((other, d))

        # Nodes-to-cluster ratio
        NC = graph_x * graph_y / Rc**2
        NNavg = N / NC

        # Compute twait for each node
        for ni in self._graph.nodes():
            node = self._get_node(ni)
            NNi = len(node.neighbourList)

            if NNi == 0:
                node.twait = 1000
                continue

            ICDi = sum(d for (_, d) in node.neighbourList) / NNi

            if NNi > NNavg:
                node.twait = (alpha * (ICDi / Rc) +
                              (1 - alpha) * (1 - NNi / N) * (1 - (NNi - NNavg) / N))
            else:
                node.twait = alpha * (ICDi / Rc) + (1 - alpha) * (1 - NNi / N)

    def _select_states(self):
        """Assign node states (CH, Sub-CH, Ordinary) based on twait ordering."""
        sorted_nodes = sorted(self._graph.nodes(),
                               key=lambda n: self._get_node(n).twait)
        for n in sorted_nodes:
            node = self._get_node(n)
            if node.state == NodeType.ASLEEP:
                node.state = NodeType.AWAKE
            node.select_state()

    def _create_clusters(self):
        """Form clusters by having each node select a parent."""
        sorted_nodes = sorted(self._graph.nodes(),
                               key=lambda n: self._get_node(n).twait)
        bs_node = self._get_node(self._base_station)
        for n in sorted_nodes:
            self._get_node(n).select_parent(bs_node)

    # ══════════════════════════════════════════
    #  Election algorithms
    # ══════════════════════════════════════════

    def elect_new_head(self, ni, threshold):
        """
        Current CH/Sub-CH evaluates whether to hand off leadership.
        Returns an UPDATE_HEAD or UPDATE_NOHEAD message, or None if score is above threshold.
        """
        node = self._get_node(ni)
        state_value = node.state.value

        if node.overall_score > threshold:
            return None

        # Find eligible children: one tier below, with score above threshold
        candidates = [
            self._get_node(child_id) for child_id in node.chdList
            if (self._get_node(child_id).state.value == state_value + 1 and
                node.chdList[child_id].overall_score > threshold)
        ]

        tmp_children = {i: Child(c.node, c.state, tdma_slot=c.tdma_slot)
                        for i, c in node.chdList.items()}

        if candidates:
            new_head = min(candidates, key=lambda c: _dist(node, c))
            msg = {
                "newHead": new_head.id,
                "chdList": tmp_children,
                "oldHead": node.id,
                "oldParent": node.parent.node.id,
                "oldHeadSchd": (node.tdmaSlot, node.totalSlots),
                "type": "UPDATE_HEAD",
            }
            node.chdList = {}
            node.parent.node = new_head
            node.state = NodeType(state_value + 1)
            return msg

        # No eligible candidate: merge children into parent
        msg = {
            "chdList": tmp_children,
            "oldHead": node.id,
            "newHead": node.parent.node.id,
            "type": "UPDATE_NOHEAD",
        }
        node.chdList = {}
        return msg

    def elect_new_head_orphans(self, ni, msg, threshold):
        """Elect a new head from orphaned nodes requesting to join."""
        node = self._get_node(ni)
        orphan_list = msg["chdList"]

        # Determine what state the new head should be
        first_orphan = next(iter(orphan_list.values()))
        if first_orphan.state == NodeType.ORDINARY:
            target_state = NodeType.SUBCLUSTER_HEAD
        else:
            target_state = NodeType.CLUSTER_HEAD

        candidates = [
            self._get_node(child_id) for child_id in orphan_list
            if (self._get_node(child_id).state.value == target_state.value + 1 and
                orphan_list[child_id].overall_score > threshold)
        ]

        if candidates:
            new_head = min(candidates, key=lambda c: _dist(node, c))
            node.chdList[new_head.id] = Child(new_head, state=new_head.state)
            self.create_TDMA_schedule(ni)
            self.spawn_TDMA_packets(ni)
            return {
                "newHead": new_head.id,
                "chdList": orphan_list,
                "type": "UPDATE_HEAD_ORPHAN",
            }

        # No candidate: absorb all orphans as children
        node.chdList.update(orphan_list)
        self.create_TDMA_schedule(ni)
        self.spawn_TDMA_packets(ni)
        return None

    # ══════════════════════════════════════════
    #  Election message handlers
    # ══════════════════════════════════════════

    def update_new_head(self, ni, msg):
        """Process UPDATE_HEAD message: reassign roles between old head, new head, and parent."""
        node = self._get_node(ni)

        if node.id == msg["newHead"]:
            # This node is promoted to head
            node.state = NodeType(node.state.value - 1)
            # Demote existing children one tier
            for child_id in node.chdList:
                child = self._get_node(child_id)
                child.state = NodeType(child.state.value - 1)
            # Absorb transferred children + old head
            node.chdList.update(msg["chdList"])
            old_head_node = self._get_node(msg["oldHead"])
            node.chdList[msg["oldHead"]] = Child(old_head_node, state=old_head_node.state)
            del node.chdList[ni]
            # Set parent
            node.parent = Parent()
            node.parent.node = self._get_node(msg["oldParent"])
            node.tdmaSlot = msg["oldHeadSchd"][0]
            node.totalSlots = msg["oldHeadSchd"][1]
            self.create_TDMA_schedule(ni)
            self.spawn_TDMA_packets(ni)

        elif node.id == msg["oldParent"]:
            # Swap old head for new head in child list
            old_slot = node.chdList[msg["oldHead"]]
            del node.chdList[msg["oldHead"]]
            node.chdList[msg["newHead"]] = old_slot

        else:
            # Regular child: update parent reference
            node.parent = Parent()
            node.parent.node = self._get_node(msg["newHead"])

    def update_no_head(self, ni, msg):
        """Process UPDATE_NOHEAD message: merge children into the old head's parent."""
        node = self._get_node(ni)

        if node.id in msg["chdList"]:
            node.parent = Parent()
            node.parent.node = self._get_node(msg["newHead"])
            old_head_state = self._get_node(msg["oldHead"]).state
            if node.parent.node.state != old_head_state:
                node.state = NodeType(node.parent.node.state.value + 1)

        elif node.id == msg["newHead"]:
            node.chdList.update(msg["chdList"])
            self.create_TDMA_schedule(ni)
            ready = node.action != Action.ELECTION
            self.spawn_TDMA_packets(ni, ready)

    def update_new_head_orphan(self, ni, msg):
        """Process UPDATE_HEAD_ORPHAN message: promote an orphan to head."""
        node = self._get_node(ni)

        if node.id == msg["newHead"]:
            node.state = NodeType(node.state.value - 1)
            for child_id in list(node.chdList):
                child = self._get_node(child_id)
                child.state = NodeType(child.state.value - 1)
            node.chdList.update(msg["chdList"])
            del node.chdList[ni]
            self.create_TDMA_schedule(ni)
            self.spawn_TDMA_packets(ni)
        else:
            node.parent = Parent()
            node.parent.node = self._get_node(msg["newHead"])

    # ══════════════════════════════════════════
    #  Orphan detection (TEAM-C only)
    # ══════════════════════════════════════════

    def observe_parent_potential(self, ni, threshold):
        """Check if this node's parent is still viable. Returns (message, new_parent) or (None, None)."""
        node = self._get_node(ni)

        if node.id in self._destroyed or node.id == self._base_station:
            return None, None
        if node.parent.worthiness_score > threshold:
            return None, None

        closest_ch = self._find_closest_ch(node)
        if closest_ch is None:
            return None, None

        node.parent = Parent()
        node.parent.node = closest_ch

        return {"child": node, "type": "REQUEST_PARENT"}, closest_ch

    def _find_closest_ch(self, node: Node):
        """Find the closest cluster head this node can connect to."""
        if node.state == NodeType.CLUSTER_HEAD:
            # CH looks in broadcast range first, then relay range
            result = self._search_for_ch(node, node.broadcastList)
            if result is None:
                result = self._search_for_ch(node, node.relayList)
        else:
            # Non-CH looks in neighbour range, then promotes itself and looks wider
            result = self._search_for_ch(node, node.neighbourList)
            if result is None:
                node.state = NodeType.CLUSTER_HEAD
                result = self._search_for_ch(node, node.broadcastList)
                if result is None:
                    result = self._search_for_ch(node, node.relayList)

        # Fallback to base station
        if result is None:
            result = self._get_node(self._base_station)

        return result

    def _search_for_ch(self, node: Node, candidates: list) -> Node | None:
        """Search a list of (neighbor, distance) tuples for the closest viable CH."""
        best = None
        best_dist = float('inf')

        for neighbor, dist in candidates:
            if (neighbor.state == NodeType.CLUSTER_HEAD and
                    node.parent.node != neighbor and
                    neighbor.id not in node.chdList and
                    neighbor.id not in self._destroyed and
                    dist < best_dist):
                best = neighbor
                best_dist = dist

        return best

    # ══════════════════════════════════════════
    #  Rendering helpers
    # ══════════════════════════════════════════

    def get_packet_render_positions(
        self, layout: LayoutResult,
    ) -> list[tuple[float, float, int, bool]]:
        """(x, y, packet_id, is_delivered) for every active/delivered packet."""
        pos = layout.positions
        results: list[tuple[float, float, int, bool]] = []

        for pkt in self._packets:
            if pkt.status == PacketStatus.DROPPED:
                continue
            if pkt.status == PacketStatus.DELIVERED:
                bx, by = pos[pkt.destination]
                results.append((bx, by, pkt.packet_id, True))
                continue

            cur = pkt.current_node
            nxt = pkt.next_node
            if nxt is None:
                cx, cy = pos[cur]
            else:
                x0, y0 = pos[cur]
                x1, y1 = pos[nxt]
                t = pkt.progress
                cx = x0 + (x1 - x0) * t
                cy = y0 + (y1 - y0) * t
            results.append((cx, cy, pkt.packet_id, False))

        return results

    def purge_delivered(self, keep_last: int = 8) -> None:
        """Remove old delivered packets to avoid unbounded memory growth."""
        delivered = [p for p in self._packets if p.is_delivered]
        if len(delivered) > keep_last:
            remove_ids = {p.packet_id for p in delivered[:-keep_last]}
            self._packets = [p for p in self._packets
                             if p.packet_id not in remove_ids]

    # ══════════════════════════════════════════
    #  Statistics
    # ══════════════════════════════════════════

    def network_dead(self) -> bool:
        """True if no packets were delivered in the last measurement interval."""
        return self._delivered_interval == 0

    def throughput(self):
        """Record packets received at BS this interval, then reset counter."""
        self._throughputs.append(self._received_packets_at_BS)
        self._received_packets_at_BS = 0

    def avg_throughput(self) -> float:
        """Average packets received at BS per measurement interval."""
        if not self._throughputs:
            return 0
        return sum(self._throughputs) / len(self._throughputs)
