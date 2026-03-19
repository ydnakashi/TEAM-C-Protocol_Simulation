"""
network_model.py — Model Layer
===============================
Owns the NetworkX graph, packet simulation state, and every
network-related operation.  Has ZERO knowledge of tkinter,
matplotlib, or any GUI framework.

NetworkX functions used (★):
  ★ nx.Graph()                     — create undirected graph
  ★ G.add_node()                   — add node with attributes
  ★ G.add_edge()                   — add weighted edge
  ★ G.remove_node()                — remove a node and its edges
  ★ G.remove_edge()                — remove a specific edge
  ★ G.clear()                      — reset the entire graph
  ★ G.nodes()                      — iterate all nodes
  ★ G.edges(data=True)             — iterate edges with attributes
  ★ G.number_of_nodes()            — node count
  ★ G.number_of_edges()            — edge count
  ★ G.degree()                     — node connectivity count
  ★ G.neighbors()                  — adjacent nodes
  ★ nx.spring_layout()             — Fruchterman-Reingold positioning
  ★ nx.get_edge_attributes()       — bulk-retrieve edge weights
  ★ nx.is_connected()              — check full reachability
  ★ nx.connected_components()      — find isolated sub-networks
  ★ nx.shortest_path()             — shortest hop path between nodes
  ★ nx.shortest_path_length()      — shortest hop distance
  ★ nx.has_path()                  — reachability check between two nodes
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import networkx as nx
from network_node import *


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
    PARENT_SELECTION = auto()
    ROUTING = auto()
    ELECTION = auto()


@dataclass
class Packet:
    """A single data packet traversing the network."""
    packet_id: int
    source: int
    destination: int
    path: list[int]                     # full hop sequence via nx.shortest_path
    hop_index: int = 0                  # which hop we're at in self.path
    progress: float = 0.0              # 0→1 interpolation between current & next hop
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
    """
    Everything the View needs to render one frame.
    No NetworkX objects — just plain data.
    """
    tick: int
    packets: list[Packet]
    base_station: int
    delivered_count: int
    dropped_count: int
    active_count: int
    events: list[str]


# ──────────────────────────────────────────────
#  The Model
# ──────────────────────────────────────────────
class NetworkModel:
    """
    Wireless network graph + discrete-tick packet simulation.
    Every public method is a pure network / simulation operation.
    """

    def __init__(self) -> None:
        self._graph: nx.Graph = nx.Graph()          # ★ nx.Graph()

        # ── Simulation state ─────────────────
        self._base_station: int = 1
        self._packets: list[Packet] = []
        self._next_packet_id: int = 1
        self._tick: int = 0
        self._delivered: int = 0
        self._dropped: int = 0
        self._spawn_interval: int = 3
        self._events: list[str] = []
        self._nodes: list[Node] = []
        self._active: list[Node] = []
        self._tdma_slot: int = 0
        self._phase: Phase = Phase.ROUTING  # Change this later

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
        self._graph.clear()                          # ★ G.clear()
        n = len(matrix)
        for i in range(n):
            self._graph.add_node(i + 1, label=f"Node {i + 1}", id=i+1, chldList={})
        for i in range(n):
            for j in range(i + 1, n):
                dist = matrix[i][j]
                if dist > 0:
                    self._graph.add_edge(i + 1, j + 1, weight=dist)

    def build_from_coordinates(
        self, coords: list[tuple[float, float]], link_range: float = 1.5
    ) -> None:
        """Build graph from (x, y) coordinates; connect pairs within link_range."""
        self._graph.clear()
        n = len(coords)
        for i in range(n):
            self._graph.add_node(i + 1, label=f"Node {i + 1}")
        for i in range(n):
            for j in range(i + 1, n):
                x0, y0 = coords[i]
                x1, y1 = coords[j]
                dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                if 0 < dist <= link_range:
                    self._graph.add_edge(i + 1, j + 1, weight=round(dist, 2))

    def compute_layout_from_coords(
        self, coords: list[tuple[float, float]]
    ) -> "LayoutResult":
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
        self._graph.remove_node(node_id)             # ★ G.remove_node()

    def add_edge(self, u: int, v: int, weight: float) -> None:
        self._graph.add_edge(u, v, weight=weight)

    def remove_edge(self, u: int, v: int) -> None:
        self._graph.remove_edge(u, v)                # ★ G.remove_edge()

    # ══════════════════════════════════════════
    #  Graph queries
    # ══════════════════════════════════════════
    def get_stats(self) -> NetworkStats:
        G = self._graph
        n_exists = G.number_of_nodes() > 0           # ★ G.number_of_nodes()
        return NetworkStats(
            num_nodes=G.number_of_nodes(),
            num_edges=G.number_of_edges(),            # ★ G.number_of_edges()
            is_connected=nx.is_connected(G) if n_exists else False,    # ★ nx.is_connected()
            num_components=nx.number_connected_components(G) if n_exists else 0,
            edges=list(G.edges(data=True)),           # ★ G.edges(data=True)
        )

    def has_edges(self) -> bool:
        return self._graph.number_of_edges() > 0

    def get_nodes(self) -> list[int]:
        return sorted(self._graph.nodes())            # ★ G.nodes()

    def get_neighbors(self, node_id: int) -> list[int]:
        return list(self._graph.neighbors(node_id))   # ★ G.neighbors()

    def get_degree(self, node_id: int) -> int:
        return self._graph.degree(node_id)            # ★ G.degree()

    def get_shortest_path(self, source: int, target: int) -> list[int]:
        return nx.shortest_path(self._graph, source, target)  # ★ nx.shortest_path()

    def get_shortest_path_length(self, source: int, target: int) -> int:
        return nx.shortest_path_length(self._graph, source, target)

    # ── Layout ───────────────────────────────
    def compute_layout(self, seed: int = 42) -> LayoutResult:
        G = self._graph
        n = G.number_of_nodes()
        positions = nx.spring_layout(G, seed=seed, k=2.5 / (n ** 0.5))  # ★ nx.spring_layout()
        node_labels = {nd: f"N{nd}" for nd in G.nodes()}
        raw = nx.get_edge_attributes(G, "weight")     # ★ nx.get_edge_attributes()
        edge_labels = {k: f"{v:.0f} m" for k, v in raw.items()}
        return LayoutResult(positions=positions,
                            node_labels=node_labels,
                            edge_labels=edge_labels)

    # ══════════════════════════════════════════
    #  Simulation engine
    # ══════════════════════════════════════════
    def set_base_station(self, node_id: int) -> None:
        if node_id not in self._graph.nodes():
            raise ValueError(f"Node {node_id} not in graph")
        self._base_station = node_id
        self._graph.nodes[node_id]["waiting"] = 8  # Replace this with the number of children

    def reset_simulation(self) -> None:
        """Clear all packets and counters; keep graph + base station."""
        self._packets.clear()
        self._next_packet_id = 1
        self._tick = 0
        self._delivered = 0
        self._dropped = 0
        self._events.clear()

    def get_source_nodes(self) -> list[int]:
        """Non-base nodes that have a path to the base station."""
        srcs = []
        self._graph.nodes[self._base_station]["chldList"] = {}

        for nd in self._graph.nodes():
            if nd == self._base_station:
                continue
            if nx.has_path(self._graph, nd, self._base_station):  # ★ nx.has_path()
                srcs.append(nd)
                self._graph.nodes[self._base_station]["chldList"][nd] = nd    # Temporary child node testing
                self._graph.nodes[nd]["tdmaSlot"] = nd
                self._graph.nodes[nd]["totalSlots"] = 8+1  # total slots + 1
        return sorted(srcs)

    def spawn_packet(self, source: int | None = None) -> Packet | None:
        """
        Create a packet at *source* (random if None) routed to base
        via nx.shortest_path.  Returns the Packet or None.
        """
        # sources = self.get_source_nodes()
        # if not sources:
        #     return None
        # if source is None:
        #     source = random.choice(sources)
        # elif source not in sources:
        #     return None

        # CHANGE THIS PART TO ROUTING TO PARENT NODE
        try:
            path = nx.shortest_path(                    # ★ nx.shortest_path()
                self._graph, source=source,
                target=self._base_station, weight="weight",
            )
        except nx.NetworkXNoPath:
            return None

        pkt = Packet(
            packet_id=self._next_packet_id,
            source=source,
            destination=path[1], # CHANGE THIS TO PARENT
            path=path[:2],  # CHANGE THIS TO [node, parent]
        )
        self._next_packet_id += 1
        self._packets.append(pkt)
        return pkt

    def tick(self) -> SimulationSnapshot:
        """
        Advance one discrete time step.
          1. Auto-spawn packets on interval
          2. Interpolate each in-transit packet forward
          3. Snap to next hop when progress >= 1
          4. Mark DELIVERED when base station reached
        """
        self._tick += 1
        self._events = []
        SPEED = 0.20        # fraction-of-hop per tick
        nodes = self.get_source_nodes()
        delivered = [p for p in self._packets if p.is_delivered]

        # Routing phase
        if(self._phase == Phase.ROUTING and len(delivered) == len(self._packets)):
            
            # Change to next phase if routing is finished
            if(self._graph.nodes[self._base_station]["waiting"] == 0):  # Add a variable that tracks how many children sent packets? issue with lost packets, might need a counter per CH for how long to wait until marking it as lost and to move on
                self._phase = Phase.ELECTION
                self._graph.nodes[self._base_station]["waiting"] = 8  # reset back to # of children

            # Continue routing when all packets have made it to next-hop
            elif (self._tick % self._spawn_interval == 0):
                
                self._tdma_slot+=1  # Start a new TDMA slot if all packets reached the next-hop

                # ── Create packets ───────────────────────
                # if self._tick % self._spawn_interval == 0:
                for node in nodes:
                    # ADD CHECK TO SEE IF NODE RECEIVED ALL NODES FROM CHILDREN (lost packets?)
                    if self._tdma_slot % self._graph.nodes[node]["totalSlots"] == self._graph.nodes[node]["tdmaSlot"]:
                        pkt = self.spawn_packet(node)
                        if pkt:
                            route_str = " → ".join(str(n) for n in pkt.path)
                            self._events.append(
                                f"[Tick {self._tick:>4}]  PKT #{pkt.packet_id:>3} "
                                f"spawned at Node {pkt.source}   route: {route_str}"
                            )
        
        # Init phase
        elif (self._phase == Phase.INIT_ROLES):
            pass

        # Parent selection
        elif(self._phase == Phase.PARENT_SELECTION):
            pass

        # S_CH/CH election
        elif(self._phase == Phase.ELECTION):
            pass

        # ── Move packets ─────────────────────
        for pkt in self._packets:
            if pkt.status != PacketStatus.IN_TRANSIT:
                continue

            pkt.progress += SPEED

            while pkt.progress >= 1.0 and pkt.status == PacketStatus.IN_TRANSIT:
                pkt.progress -= 1.0
                pkt.hop_index += 1

                # Check arrival at base station
                if pkt.hop_index >= len(pkt.path) - 1:
                    pkt.hop_index = len(pkt.path) - 1
                    pkt.progress = 0.0
                    pkt.status = PacketStatus.DELIVERED
                    self._delivered += 1
                    self._events.append(
                        f"[Tick {self._tick:>4}]  PKT #{pkt.packet_id:>3} "
                        f"DELIVERED → base station (Node {self._base_station})"
                    )
                    # parent = self._graph.nodes[pkt.source]["parent"]
                    # self._graph.nodes[parent]["waiting"] -= 1
                    self._graph.nodes[self._base_station]["waiting"]-=1  # temporary BS code

        self._active = [p for p in self._packets if p.status == PacketStatus.IN_TRANSIT]

        return SimulationSnapshot(
            tick=self._tick,
            packets=list(self._packets),
            base_station=self._base_station,
            delivered_count=self._delivered,
            dropped_count=self._dropped,
            active_count=len(self._active),
            events=list(self._events),
        )

    def get_packet_render_positions(
        self, layout: LayoutResult,
    ) -> list[tuple[float, float, int, bool]]:
        """
        (x, y, packet_id, is_delivered) for every packet.
        Positions are interpolated between hops using the layout coords.
        """
        pos = layout.positions
        results: list[tuple[float, float, int, bool]] = []

        for pkt in self._packets:
            if pkt.status == PacketStatus.DROPPED:
                continue
            if pkt.status == PacketStatus.DELIVERED:
                bx, by = pos[self._base_station]
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
        """Remove old delivered packets to avoid unbounded memory."""
        delivered = [p for p in self._packets if p.is_delivered]
        if len(delivered) > keep_last:
            remove_ids = {p.packet_id for p in delivered[:-keep_last]}
            self._packets = [p for p in self._packets
                             if p.packet_id not in remove_ids]

    # ── Utility ──────────────────────────────
    def summary(self) -> str:
        s = self.get_stats()
        conn = "connected" if s.is_connected else f"{s.num_components} components"
        return f"Nodes: {s.num_nodes}  |  Edges: {s.num_edges}  |  {conn}"

    def nx_functions_used(self) -> list[str]:
        return [
            "nx.Graph()", "G.add_node()", "G.add_edge()",
            "G.remove_node()", "G.remove_edge()", "G.clear()",
            "G.nodes()", "G.edges(data=True)",
            "G.number_of_nodes()", "G.number_of_edges()",
            "G.degree()", "G.neighbors()",
            "nx.spring_layout()", "nx.get_edge_attributes()",
            "nx.is_connected()", "nx.connected_components()",
            "nx.shortest_path()", "nx.shortest_path_length()",
            "nx.has_path()",
        ]