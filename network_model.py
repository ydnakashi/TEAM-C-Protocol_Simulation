"""
network_model.py — Model Layer
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
import copy

import networkx as nx
# from network_node import *
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
    path: list[int]                     # full hop sequence via nx.shortest_path
    content: dict
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
    dead: bool

class Protocol(Enum):
    MI2RSDiC = auto()
    TEAM_C = auto()

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
        self._phase: Phase = Phase.INIT_ROLES
        self._loss_interval: int = 3   # change this later
        self._destroyed_prob: dict = {}
        self._destroyed: set[int] = set()
        self._to_remove: set[int] = set()
        self._recieved_poweracks: int = 0
        self._received_packets_at_BS: int = 0
        self._throughputs = []
        self._delivered_interval = 1

        # self._nodes_to_destroy : list[int] = [9, 11, 15, 3]  #, 9, 11, 6]
        self._nodes_to_destroy: list[int] = [9, 2]

        # Switch based on protocol to run
        # self._protocol: Protocol = Protocol.MI2RSDiC
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
        self._graph.clear()                          # ★ G.clear()
        n = len(matrix)
        for i in range(n):
            self._graph.add_node(i + 1, label=f"Node {i + 1}")
        for i in range(n):
            for j in range(i + 1, n):
                dist = matrix[i][j]
                if dist > 0:
                    self._graph.add_edge(i + 1, j + 1, weight=dist)

    def build_from_coordinates(self, coords: list[tuple[float, float]], link_range: float = 2.0) -> None:
        self._graph.clear()
        n = len(coords)
        for i in range(n):
            node_id = i + 1  
      
            if node_id == 6:
                randomBattery = 30
            elif node_id == 7:
                randomBattery = 100
            elif node_id == 4: 
                randomBattery = 75
            else:
                randomBattery = randomizeBattery(node_id)
            
            
            self._graph.add_node(i+1, label=f"Node{i+1}", node=(Node(id=node_id, powerPercent=randomBattery,coords=[coords[i][0], coords[i][1]], Rc=link_range))
            )
        # self._graph.add_node(Node())
        for i in range(n):
            for j in range(i + 1, n):
                x0, y0 = coords[i]
                x1, y1 = coords[j]

                dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                if 0 < dist <= link_range:
                    id_i = i + 1
                    id_j = j + 1

                    self._graph.add_edge(
                        id_i, id_j,
                        weight=round(dist, 2)
                    )

      
        # print("TEST ID", node[1].id)

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
        self._graph.nodes[node_id]["node"].state = NodeType.BASE_STATION

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

        for nd in self._graph.nodes():
            if nd == self._base_station:
                continue
            if nx.has_path(self._graph, nd, self._base_station):  # ★ nx.has_path()
                srcs.append(nd)
        return sorted(srcs)
    
    def get_parent_nodes(self) -> list[int]:
        """Nodes that have children."""
        parents = []
        for nd in self._graph.nodes():
            if len(self._graph.nodes[nd]["node"].chdList) > 0:
                parents.append(nd)

        return sorted(parents)

    # Do we even need this? idk
    def get_ordinary_nodes(self) -> list[int]:
        pass

    def init_actions(self):
        # Send data if no children
        for ni in self._graph.nodes():
            if (len(self._graph.nodes[ni]["node"].chdList) == 0):
                self._graph.nodes[ni]["node"].action = Action.SEND_DATA

    def create_TDMA_schedule(self, ni):
        """Create TDMA schedule for node's children"""
        slot = 0
        total = 0
        node = self._graph.nodes[ni]["node"]
        for id, child in node.chdList.items():
            self._graph.nodes[id]["node"].tdmaSlot = slot
            child.tdma_slot = slot
            slot += 1
            total += 1
        
        # self._graph.nodes[node]["node"].waiting = total  # Total time slots
        node.resetWaiting()
        node.timer = -1  # max time to wait before declaring lost packet
        for id, child in node.chdList.items():
            self._graph.nodes[id]["node"].totalSlots = total

    def spawn_TDMA_packets(self, parent, ready=True):
        """Spawn packets to inform children of their TDMA slot"""
        for child in self._graph.nodes[parent]["node"].chdList:
            # Pass the schedule to the children
            schedule = {id: c.tdma_slot for id, c in self._graph.nodes[parent]["node"].chdList.items()}
            msg = {
                "schd": schedule,
                "tt": len(self._graph.nodes[parent]["node"].chdList),
                "ready": ready,
                "type": "MEMBERACK"   
            }
            pkt = self.spawn_packet(msg, parent, child)
            # parent.send_memberack_message(msg, child)

    def update_TDMA_slot(self, node: int, slot: int, total_slots: int):
        """Record TDMA schedule information when received by parent."""
        self._graph.nodes[node]["node"].tdmaSlot = slot
        self._graph.nodes[node]["node"].totalSlots = total_slots
        return node
    
    def calculate_worthiness_score(self, L, N, c=1):
        if(N == 0): return 0
        if(L > N): return 1
        t = L/N
        r = 1 - (((12*L*(N-L))**0.5) / ((N+1)*N))
        w = 1 - (((t-1)**2 + (c**2) * (r-1)**2)**0.5 / (1+c**2)**0.5)
        proj_w = (w-0.29)/(1-0.29)
        return proj_w
    
    def spawn_battery_req(self, ready=True):
        parents = self.get_parent_nodes() 
        for id in parents:
            for child in self._graph.nodes[id]["node"].chdList:
                msg = {
                    "ready": ready,
                    "type": "POWERREQ",
                    "parentPower": self._graph.nodes[id]["node"].power
                }
                pkt = self.spawn_packet(msg, id, child)
    
 
    def startWorthinessCalc(self):
        for ni in self._graph.nodes: 
            if ni in self._destroyed or self._to_remove:
                continue
            node = self._graph.nodes[ni]["node"]
            # calculate parents score  
            parent_worthiness = self.calculate_worthiness_score(node.parent.L, node.parent.N)
            # print(ni, " power: ", node.powerPercent)
            # print("ID, worthyscore, L, N", node.id, parent_worthiness, node.parent.L, node.parent.N)
            
            w_weight = 0.5
            p_weight = 0.5
            if self._protocol == Protocol.MI2RSDiC:
                w_weight = 0
                p_weight = 1

            # Calculate worthiness score
            parent_overall_score = w_weight * parent_worthiness + (p_weight * (node.parent.powerPercent/100))
            
            node.parent.overall_score = parent_overall_score
            node.parent.L = 0
            node.parent.N = 0
            node.parent.worthiness_score = parent_worthiness
            # print("current id, parent score", node.id, node.parent.overall_score)
            
            # calculate childrens score
            for chdId, childObj in node.chdList.items():
                child_worthiness = self.calculate_worthiness_score(childObj.L, childObj.N)
                # if child_worthiness <= 0:
                #     print("destroyed: ", chdId)
                #     self._to_remove.add(chdId)
                child_overall_score = 0.5 * child_worthiness + (0.5 * (childObj.powerPercent/100))
                childObj.overall_score = child_overall_score
                childObj.N = 0
                childObj.L = 0
                # print("childId, child score: ", chdId, child_overall_score)

        for ni in self._graph.nodes:
            node = self._graph.nodes[ni]["node"]
            if node.state == NodeType.DEAD:
                self.target_destroy(False, ni)
                # node.timer = -1
                # node.parent.node.chdList.pop(node.id, None)
                # self._graph.nodes[ni]["node"] = Node(ni)  # wipe the data
        # self.redo_edges()


            
            
    def cleanup_dead_nodes(self):
        for ni in self._graph.nodes:
            # if ni == 1:
            #     continue
            node = self._graph.nodes[ni]["node"]
            if node.id in self._to_remove:
                self._destroyed.add(node.id)
    
                if node.parent is not None:
                    node.parent.node.chdList.pop(node.id, None)

                # for childId in list(node.chdList.keys()):
                #     child = self._graph.nodes[childId]["node"]
                #     child.parent = None
                #     # child.action = Action.ORPHAN_ELECTION
                #     child.await_parent = False
        
        self._to_remove.clear()
        self.redo_edges()

        # self._graph.remove_node(ni)

    
    def init_destruction_probabilities(self, max=40):
        """Initialize destruction probabilities (0-100) for each node"""
        random.seed(42)
        for ni in self.get_source_nodes():
            self._destroyed_prob[ni] = random.randrange(0, max)
        # print(self._destroyed_prob)

    def destroy_nodes(self):
        """Randomly destroy nodes based on their probabilities"""
        # cap at 5
        if len(self._destroyed) > 4:
            return
        new_destroyed = []
        random.seed(42)
        # for ni, prob in self._destroyed_prob.items()::
        for ni, prob in self._destroyed_prob.items():
            if (random.randrange(0, 100)) < prob and (ni not in self._destroyed):
                node = self._graph.nodes[ni]["node"]
                # self._destroyed.add(ni)
                node.timer = -1
                node.powerPercent = 0
                new_destroyed.append(ni)
                # self._destroyed.add(self._graph.nodes[ni]["node"].id)
                node.state = NodeType.DEAD
                node.parent.node.chdList.pop(node.id, None)
    
                self._destroyed.add(node)
                # self._graph.nodes[ni]["node"] = Node(ni)  # wipe the data
                # print("new destorted: ", self._destroyed)
                self._events.append(f"Destroyed nodes: {new_destroyed}")
                self.redo_edges()
                return
        print("destoryed: ", self._destroyed)

    def target_destroy(self, random_destroy, id=0):
       
        if random_destroy == True and len(self._nodes_to_destroy) > 0:
            id = self._nodes_to_destroy[0]
            self._nodes_to_destroy.pop(0)

        elif random_destroy == True and len(self._nodes_to_destroy) <= 0:
            return

        self._destroyed.add(id)
        node = self._graph.nodes[id]["node"]
        node.timer = -1
        node.powerPercent = 0
        # self._destroyed.append(self._graph.nodes[id]["node"].id)
        node.state = NodeType.DEAD

        node.parent.node.chdList.pop(node.id, None)
        # self._graph.nodes[ni]["node"] = Node(ni)  # wipe the data
        print("destroyed: ", self._destroyed)

        self.redo_edges()


    # def reset_routing(self):
    #     for ni in self._graph.nodes:
    #         node = self._graph.nodes[ni]["node"]
    #         # node.sent = False
    #         node.waiting = len(node.chdList)
    #         node.timer = self._loss_interval * node.waiting
    #         # for ci, child in node.chdList.items():
    #         #     child.received = False

    #     self._graph.nodes[self._base_station]["node"].waiting = len(self._graph.nodes[self._base_station]["node"].chdList)

    def init_TDMA(self):
        parents = self.get_parent_nodes()
        for parent in parents:
            self.create_TDMA_schedule(parent)  # Create TDMA schedules for all children
            self.spawn_TDMA_packets(parent)
    
    def redo_edges(self):
        
        self._graph.clear_edges()
        for ni in self._graph.nodes:
            node = self._graph.nodes[ni]["node"]
            if node.id in self._destroyed:
                continue  
            for chdId, chdObj in node.chdList.items():
                self._graph.add_edge(node.id, chdId)

    def spawn_packet(self, content: dict, source: int, dest: int) -> Packet | None:
        """
        Create a packet at *source* (random if None) routed to base
        via nx.shortest_path.  Returns the Packet or None.
        """
        pkt = Packet(
            packet_id=self._next_packet_id,
            source=source,
            destination=dest,
            path=[source, dest],
            content=content
        )
        self._next_packet_id += 1
        self._packets.append(pkt)

        if pkt:
            route_str = " → ".join(str(n) for n in pkt.path)
            self._events.append(
                f"[Tick {self._tick:>4}]  PKT #{pkt.packet_id:>3} {pkt.content['type']} "
                f"spawned at Node {pkt.source}   route: {route_str}"
            )
            sourceNode = self._graph.nodes[source]['node']
            destNode = self._graph.nodes[dest]['node']
            sourceNode.send(content, destNode, self.dist(sourceNode, destNode))
        return pkt

    def destroy_packets(self, pck):
        # packet dropped 
        if random.random() < 0.02:
            pck.status = PacketStatus.DROPPED
    

    def move_packets(self):
        SPEED = 0.10  # fraction-of-hop per tick

        for pkt in self._packets:
            if pkt.status != PacketStatus.IN_TRANSIT:
                continue
            
            pkt.progress += SPEED

            while pkt.progress >= 1.0 and pkt.status == PacketStatus.IN_TRANSIT:
                pkt.progress -= 1.0
                pkt.hop_index += 1

                # Check arrival at destination
                if pkt.hop_index >= len(pkt.path) - 1:
                    if pkt.status != PacketStatus.DROPPED:
                        pkt.hop_index = len(pkt.path) - 1
                        pkt.progress = 0.0
                        pkt.status = PacketStatus.DELIVERED
                        self._delivered += 1
                        if pkt.destination == self._base_station:
                            self._delivered_interval += 1
                        self._events.append(
                            f"[Tick {self._tick:>4}]  PKT #{pkt.packet_id:>3} "
                            f"DELIVERED → Node {pkt.destination}"
                        )

                    node = self._graph.nodes[pkt.destination]["node"]
                    if(pkt.destination in self._destroyed): continue   # don't do anything if node is destroyed
                   
                    if(pkt.content["type"] == "DATA_MSG"):
                        # node.chdList[pkt.source].received = True
                        # node.action = Action.SEND_DATA_ACK  # send ACK back
                        if(pkt.source not in node.chdList): continue
                        node.chdList[pkt.source].powerPercent = pkt.content["power"]
                        node.pkt = pkt

                        # for throughput calculation
                        if(pkt.destination == self._base_station): self._received_packets_at_BS += 1

                    elif(pkt.content["type"] == "MEMBERACK"):  # Update node's tdma slot received
                        # node.tdmaSlot = pkt.content["schd"][pkt.destination]
                        # node.totalSlots = pkt.content["tt"]
                        if(pkt.source != node.parent.node.id): continue
                        self.update_TDMA_slot(pkt.destination, pkt.content["schd"][pkt.destination], pkt.content["tt"])
                        if(len(node.chdList) == 0 and (node.action == Action.ELECTION or node.action == Action.IDLE)):   # pkt.content["ready"] and
                            node.action = Action.SEND_DATA
                        elif(node.action == Action.ORPHAN_ELECTION):
                            node.action = Action.ELECTION
                        node.await_parent = False
                        # node.ready_to_send = pkt.content["ready"]

                    elif(pkt.content["type"] == "DATA_ACK"):
                        # node.p_rcvd = True
                        if node.parent is None:
                            pkt.status = PacketStatus.DROPPED
                            continue

                        if(self._protocol == Protocol.MI2RSDiC):
                            node.action = Action.ELECTION
                        elif(not node.await_parent and node.action != Action.AWAIT_REQS):  
                            node.action = Action.ORPHAN_ELECTION    

                        node.parent.L += 1
                        node.parent.powerPercent = pkt.content["power"]
                        node.overall_score = pkt.content["overall_score"]
                        # node.action = Action.ELECTION
                        node.ready_to_send = True

                    elif(pkt.content["type"] == "UPDATE_HEAD"):
                        self.update_new_head(pkt.destination, pkt.content)
                        self.redo_edges()
                    
                    elif(pkt.content["type"] == "UPDATE_NOHEAD"):
                        self.update_no_head(pkt.destination, pkt.content)
                        self.redo_edges()
                    
                    elif(pkt.content["type"] == "UPDATE_HEAD_ORPHAN"):
                        self.update_new_head_orphan(pkt.destination, pkt.content)
                        self.redo_edges()

                    elif(pkt.content["type"] == "UPDATE_NOHEAD_ORPHAN"):
                        self.update_no_head_orphan(pkt.destination, pkt.content)
                        self.redo_edges()
                    
                    elif(pkt.content["type"] == "READY"):
                        if(pkt.source != node.parent.node.id): continue
                        if (len(node.chdList) == 0 and (node.action == Action.ELECTION or node.action == Action.IDLE)):
                            node.action = Action.SEND_DATA
                        elif(node.action == Action.ORPHAN_ELECTION):
                            node.action = Action.ELECTION
                        node.ready_to_send = True

                    elif(pkt.content["type"] == "REQUEST_PARENT"):
                        # node waits a certain amount of time before doing elect_head_orphan?
                        if(node.orphan_timer == -1): node.orphan_timer = self._loss_interval   # set to something
                        if(pkt.destination == self._base_station): print("REQUEST PARENT ", node.orphan_timer)
                        # adds all the pkt.sources to a list
                        node.orphans[pkt.source] = Child(self._graph.nodes[pkt.source]["node"], self._graph.nodes[pkt.source]["node"].state, 
                                                         overall_score=self._graph.nodes[pkt.source]["node"].overall_score)
                        node.action = Action.AWAIT_REQS

                       
    def send_data_packet(self, ni):
        node = self._graph.nodes[ni]["node"]
        # print(ni, node.parent.node.id, node.parent.node.chdList)

        if (node.parent == None) or (ni not in node.parent.node.chdList):
            return
        node.parent.node.chdList[ni].N += 1  # parent observes that the child should be sending a packet in this time slot

        # print(self._destroyed)
        if (ni not in self._destroyed):
            node.parent.N += 1

            msg = {
                "power": node.powerPercent,
                "type": "DATA_MSG"
            }
            pkt = self.spawn_packet(msg, ni, node.parent.node.id)
            # node.sent = True
            node.action = Action.IDLE
            node.timer = self._loss_interval  # Set timer for ACK packet to be returned from parent
            node.orphan_timer = -1  # reset timer
            node.orphans = {}  # delete orphans
            # node.waiting = len(node.chdList)
            node.resetWaiting()
            node.timer = self._loss_interval * len(node.chdList)
            node.ready_to_send = False

    def send_data_ack(self, pkt):
        # CH doesnt even know it has this child and it was their turn to send so nithing happens
        # i think
        node = self._graph.nodes[pkt.destination]["node"]
        if pkt.source not in node.chdList:
            node.action = Action.IDLE
            return

        if(node.timer <= -1):
            node.timer = self._loss_interval * len(node.chdList)

        # node.waiting-=1 
        self.spawn_packet({
            "power": node.powerPercent,
            "overall_score": node.chdList[pkt.source].overall_score,
            "type": "DATA_ACK"
            }, pkt.destination, pkt.source)
        node.chdList[pkt.source].L += 1
        node.pkt = None
        node.chdList[pkt.source].received = True

        # if(node != self._base_station and (node.waiting <= 0 or node.timer <= 0)): 
        #     node.action = Action.SEND_DATA
        # else:
        #     node.action = Action.IDLE
        if(node.action == Action.IDLE): node.action = Action.SEND_DATA

    def send_election_msg(self, ni, msg):
        if(msg["type"] == "UPDATE_HEAD"):
            self.spawn_packet(msg, ni, msg["oldParent"])
        elif(msg["type"] == "UPDATE_NOHEAD"):
            self.spawn_packet(msg, ni, msg["newHead"])

        for ci in msg["chdList"]:
            self.spawn_packet(msg, ni, ci)

    def send_ready_msg(self, ni):
        msg = {"type": "READY"}
        for ci in self._graph.nodes[ni]["node"].chdList:
            self.spawn_packet(msg, ni, ci)

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
        dead = False
        # nodes = self.get_source_nodes()
        # delivered = [p for p in self._packets if p.is_delivered]

        if (self._tick % self._spawn_interval == 0):

            if(self._phase == Phase.INIT_ROLES):
                self.twaitCalculation()
                self.stateSelection()
                self.clusterCreation()
                # self._graph.nodes[6]["node"].powerPercent = 35
                # self._graph.nodes[7]["node"].powerPercent = 40

                self.init_TDMA()
                self.redo_edges()

                self.init_destruction_probabilities()
                self.init_actions()

                # use the same number to get the same seeded random battery life
                # self.target_destroy(11)
                # print(self._destroyed)
                # print(self._to_remove)
                self._phase = Phase.ROUTING
            else:

                self._tdma_slot+=1  # Start a new TDMA slot if all packets reached the next-hop

                for ni in self._graph.nodes():
                    node = self._graph.nodes[ni]["node"]
                    # if (ni != self._base_station): print(ni, node.action, node.parent.overall_score, node.parent.worthiness_score, node.chdList.keys(), node.await_parent, node.parent.node.id, node.timer)
                    # if (ni == 13): print(ni, node.action, node.orphan_timer, node.chdList.keys())
                    # if(ni == 3): print(ni, node.action, node.timer, node.chdList.keys())
                    node.timer -= 1
                    # else: print(ni, node.action, node.orphan_timer, node.chdList.keys())
                    if node.state == NodeType.DEAD:
                        continue
                    orphan_msg = None
                    if(self._protocol == Protocol.TEAM_C and not node.await_parent and node.action != Action.AWAIT_REQS):
                        orphan_msg, new_head_orphan = self.observe_parent_potential(ni, 0.1)   # Random threshold for now
                        # print("orphan: ", orphan_msg)
                        if orphan_msg != None: 
                            print("orphan: ", orphan_msg)
                            node.action = Action.ORPHAN_ELECTION
                            node.await_parent = True

                    if(len(node.chdList) == 0 and node.parent and node.parent.node and node.parent.node.id == self._base_station and node.action == Action.IDLE and node.timer<=0):
                        node.action = Action.SEND_DATA
                        node.timer = self._loss_interval

                    # Send data packet during your TDMA time slot
                    if (ni != self._base_station) and (node.action == Action.SEND_DATA) and \
                        (self._tdma_slot % node.totalSlots == node.tdmaSlot) and (node.childrenWaiting() == 0 or node.timer <= 0) and \
                        (not node.await_parent):
                        # print(node.parent.node.chdList)
                        self.send_data_packet(ni)
                    
                    # Send ACK back to child when they send their data packet
                    elif (node.pkt):
                        self.send_data_ack(node.pkt)

                    # Determine to re-elect head or not
                    elif (node.action == Action.ELECTION) and \
                        (self._tdma_slot % node.totalSlots == node.tdmaSlot):

                        node.action = Action.SEND_DATA

                        if(len(node.chdList) == 0):    #  or node.ready_to_send
                            # node.action = Action.IDLE
                            # if(node.ready_to_send): node.action = Action.SEND_DATA
                            continue
                        
                        msg = self.elect_new_head(ni, 0.5)   # Random threshold for now
                        if msg == None:
                            # send no_election? small packet to tell them to continue sending data
                            self.send_ready_msg(ni)
                            node.action = Action.IDLE

                            # if(node.ready_to_send):
                            #     node.action = Action.SEND_DATA
                            # if(node.ready_to_send): node.action = Action.SEND_DATA
                            continue
                        print("election: ", msg)
                        self.send_election_msg(ni, msg)
                    elif (node.action == Action.ORPHAN_ELECTION):

                        # msg, ch = self.observe_parent_potential(ni, 0.5)   # Random threshold for now
                        # print("orphan: ", msg)
                        if orphan_msg != None:
                            # print(ch.id, msg["child"].id)
                            self.spawn_packet(orphan_msg, ni, new_head_orphan.id)
                            # node.await_parent = True
                        else:
                            node.action = Action.ELECTION
                    
                    elif (node.action == Action.AWAIT_REQS):

                        if(node.orphan_timer > 0): node.orphan_timer -= 1
                        if(ni == self._base_station): print(node.id, "ORPHAN TIMER: ", node.orphan_timer)
                        if(node.orphan_timer == 0):
                            # print("sending message for ", ni, " to ", node.orphans)
                            orph_msg = {
                                "chdList": node.orphans
                            }
                            msg = self.elect_new_head_orphans(ni, orph_msg, 0.25)  # random threshold for now
                            if(msg == None): 
                                self.send_ready_msg(ni)
                                self.redo_edges()
                            else: 
                                self.send_election_msg(ni, msg)
                            node.action = Action.ELECTION

                        # msg = self.elect_new_head(ni, 0)   # Random threshold for now
                        # # print(msg)
                        # if msg == None: 
                        #     # send no_election? small packet to tell them to continue sending data
                        #     self.send_ready_msg(ni)
                        #     # if(node.ready_to_send):
                        #     #     node.action = Action.SEND_DATA
                        #     # if(node.ready_to_send): node.action = Action.SEND_DATA
                        #     continue
                        # self.send_election_msg(ni, msg)
        # for ni in self._graph.nodes(): 
        #     print(self._graph.nodes[ni]["node"].id, self._graph.nodes[ni]["node"].state)
        
        # every so often have a chance to destory a node
        # if a node is destoryed, it gets caught in the NEXT NEXT worthiness score (as it would have had some packets being sent before it died)
        if self._tick % 150 == 0:
            self.target_destroy(True)
        if self._tick % 200 == 0:   
            self.startWorthinessCalc()
            # self.cleanup_dead_nodes()
        if self._tick % 250 == 0 and not self.network_dead():
            self.throughput()

        if self._tick % 250 == 0:
            if(self.network_dead()): dead = True
            self._delivered_interval = 0   # reset interval to determine when network dies

        # self.destroy_nodes()
        self.move_packets()
        self._active = [p for p in self._packets if p.status == PacketStatus.IN_TRANSIT]

        return SimulationSnapshot(
            tick=self._tick,
            packets=list(self._packets),
            base_station=self._base_station,
            delivered_count=self._delivered,
            dropped_count=self._dropped,
            active_count=len(self._active),
            events=list(self._events),
            dead=dead
        )
    
    def dist(self, a, b):
        x1, y1 = a.coords
        x2, y2 = b.coords
        return ((x1-x2)**2 + (y1-y2)**2)** 0.5
    
    def twaitCalculation(self, graphX=10, graphY=10, Rc=2, alpha=0.5):
        # the total amount of nodes in the graph
        N = self._graph.number_of_nodes()

        for ni in self._graph.nodes():      
            node = self._graph.nodes[ni]["node"]
        
            for oi in self._graph.nodes():
                other = self._graph.nodes[oi]["node"]
                # check that the node is not itself
                if node == other :
                    continue
               
                dist = self.dist(node, other)

                if dist <= Rc:
                    node.neighbourList.append((other, dist))
                # only nodes that are within the multipled distance but outside of Rc are added
                elif dist <= (3/2) * Rc:
                    node.broadcastList.append((other, dist))
                elif dist <= 3 * Rc:
                    node.relayList.append((other, dist))

        # nodes to cluster ratio
        NC = graphX * graphY / (Rc) ** 2
        NNavg = N / NC

        # twait calculations
        for ni in self._graph.nodes():
            node = self._graph.nodes[ni]["node"]
            NNi = len(node.neighbourList)

            if NNi == 0:
                node.twait = 1000
                continue

            # icd compute
            total_dist = sum(dist for (_, dist) in node.neighbourList)
            ICDi = total_dist / NNi
            # print("ICDI: " ,ICDi)

            if NNi > NNavg:
                twait = alpha * (ICDi / Rc) + (1 - alpha) * \
                    (1 - (NNi / N)) * (1 - ((NNi - NNavg) / N))
            else:
                twait = alpha * (ICDi / Rc) + (1 - alpha) * \
                    (1 - (NNi / N))
            node.twait = twait

    def stateSelection(self):    
        sortedNodes = sorted(self._graph.nodes(), key=lambda n: self._graph.nodes[n]["node"].twait)
        # State setting based on twait
        for n in sortedNodes:
            node = self._graph.nodes[n]["node"]
            if node.state == NodeType.ASLEEP: node.state = NodeType.AWAKE
            node.select_state()

    def clusterCreation(self):
        sortedNodes = sorted(self._graph.nodes(), key=lambda n: self._graph.nodes[n]["node"].twait)
        bsNode = self._graph.nodes[self._base_station]['node']
        for n in sortedNodes:
            node = self._graph.nodes[n]['node']
            node.select_parent(bsNode)

    # Current CH or S_CH enters the head update phase
    def elect_new_head(self, ni, Eth):
        node = self._graph.nodes[ni]["node"]
        state = node.state.value
        o_score = node.overall_score

        # print(ni, o_score)

        if (o_score > Eth): return  # do not update if energy is still high

        children = node.chdList

        # Choose a node within the children that fit the criteria
        candidates = [
            self._graph.nodes[child] for child in children
            if self._graph.nodes[child]["node"].state.value == state+1 and node.chdList[child].overall_score > Eth
        ]

        tmp_chdList = {i: Child(c.node, c.state, tdma_slot=c.tdma_slot) for i, c in node.chdList.items()}

        if candidates:
            new_head = min(candidates, key= lambda c: self.dist(node, c["node"]))  # elect smallest distance node

            # send UPDATE_HEAD with ID of new head, ChdList, ID of this node, parent ID, type of msg
            UPDATE_HEAD = {
                "newHead": new_head["node"].id,
                "chdList": tmp_chdList,  # copy.deepcopy(node.chdList)
                "oldHead": node.id,
                "oldParent": node.parent.node.id,
                "oldHeadSchd": (node.tdmaSlot, node.totalSlots),
                "type": "UPDATE_HEAD"
            }

            # delete chdList
            node.chdList = {}

            # update parent to new head
            node.parent.node = self._graph.nodes[new_head["node"].id]["node"]
            # update state
            node.state = NodeType(node.state.value + 1)

            return UPDATE_HEAD

        # send UPDATE_NOHEAD with ChdList and parent ID, NodeID, type
        UPDATE_NOHEAD = {
            "chdList": tmp_chdList,
            "oldHead": node.id,
            "newHead": node.parent.node.id,
            "type": "UPDATE_NOHEAD"
        }

        # delete ChdList
        node.chdList = {}

        return UPDATE_NOHEAD # no possible candidates

    # Elect new head within orphaned nodes
    def elect_new_head_orphans(self, ni, msg, Oth):
        node = self._graph.nodes[ni]["node"]

        find_state = NodeType.CLUSTER_HEAD
        if([*msg["chdList"].values()][0].state == NodeType.ORDINARY):
            find_state = NodeType.SUBCLUSTER_HEAD

        # Choose a node within the children that fit the criteria
        candidates = [
            self._graph.nodes[child] for child in msg["chdList"]
            if self._graph.nodes[child]["node"].state.value == find_state.value+1 and msg["chdList"][child].overall_score > Oth
        ]

        if candidates:
            new_head = min(candidates, key= lambda c: self.dist(node, c["node"]))  # elect smallest distance node
            
            # add the new head to chdList
            node.chdList[new_head["node"].id] = Child(new_head["node"], state=new_head["node"].state)
            # TDMA schedule
            self.create_TDMA_schedule(ni)
            self.spawn_TDMA_packets(ni)

            # send UPDATE_HEAD_ORPHAN with ID of new head, ChdList, ID of this node, parent ID, type of msg
            UPDATE_HEAD_ORPHAN = {
                "newHead": new_head["node"].id,
                "chdList": msg["chdList"],
                "type": "UPDATE_HEAD_ORPHAN"
            }

            return UPDATE_HEAD_ORPHAN

        # else, keep them all as children
        node.chdList.update(msg["chdList"])
        # TDMA schedule
        self.create_TDMA_schedule(ni)
        self.spawn_TDMA_packets(ni) 

        UPDATE_NOHEAD_ORPHAN = {
                "chdList": msg["chdList"],
                "type": "UPDATE_NOHEAD_ORPHAN"
            }  # no possible candidates
        
        return UPDATE_NOHEAD_ORPHAN

    # Nodes update themselves when receiving message
    def update_new_head(self, ni, msg):
        node = self._graph.nodes[ni]["node"]
        # If this is the new head, update itself as parent
        if (node.id == msg["newHead"]):
            # update state to new state
            node.state = NodeType(node.state.value - 1)
            # if chdList is not empty, update the children state to state-1
            chdList = node.chdList
            if (len(chdList) > 0):
                for child in chdList:
                    self._graph.nodes[child]["node"].state = NodeType(self._graph.nodes[child]["node"].state.value - 1)

            node.chdList.update(msg["chdList"])
            node.chdList[msg["oldHead"]] = Child(self._graph.nodes[msg["oldHead"]]["node"],
                                                 state=self._graph.nodes[msg["oldHead"]]["node"].state)
            del node.chdList[ni]

            node.parent = Parent()
            node.parent.node = self._graph.nodes[msg["oldParent"]]["node"]
            node.tdmaSlot = msg["oldHeadSchd"][0]
            node.totalSlots = msg["oldHeadSchd"][1]

            self.create_TDMA_schedule(ni)
            self.spawn_TDMA_packets(ni)  # Broadcast MEMBERACK

        elif(node.id == msg["oldParent"]):
            # Take out old head and add new head to chdList
            old_slot = node.chdList[msg["oldHead"]]
            del node.chdList[msg["oldHead"]]
            node.chdList[msg["newHead"]] = old_slot  # use the time slot of the old head

        # If this is a child, update its parent to new head
        else:
            node.parent = Parent()
            node.parent.node = self._graph.nodes[msg["newHead"]]["node"]

        return node

    # Any node that receives UPDATE_NOHEAD message udpates itself
    def update_no_head(self, ni, msg):
        node = self._graph.nodes[ni]["node"]
        # if node is one of the children from the message, update its parent to the parent in the message
        if(node.id in msg["chdList"]):
            node.parent = Parent()
            node.parent.node = self._graph.nodes[msg["newHead"]]["node"]
            if(node.parent.node.state != self._graph.nodes[msg["oldHead"]]["node"].state):
                node.state = NodeType(node.parent.node.state.value+1)

        # if the node is the parent in the message, add the children to its chdList
        elif(node.id == msg["newHead"]):
            node.chdList.update(msg["chdList"])

            # Create new TDMA schedule
            self.create_TDMA_schedule(ni)
            # print(node.id, node.action)
            ready = False if node.action == Action.ELECTION else True
            self.spawn_TDMA_packets(ni, ready)  # Broadcast MEMBERACK

        return node

    # Nodes update themselves when UPDATE_HEAD_ORPHANED message
    def update_new_head_orphan(self, ni, msg):
        node = self._graph.nodes[ni]["node"]
        # If this is the new head, update itself as parent
        if (node.id == msg["newHead"]):
            # update state to new state
            node.state = NodeType(node.state.value - 1)
            # if chdList is not empty, update the children state to state-1
            chdList = node.chdList
            if (len(chdList) > 0):
                for child in chdList:
                    self._graph.nodes[child]["node"].state = NodeType(self._graph.nodes[child]["node"].state.value - 1)

            node.chdList.update(msg["chdList"])
            
            del node.chdList[ni]

            self.create_TDMA_schedule(ni)
            self.spawn_TDMA_packets(ni)  # Broadcast MEMBERACK

        # If this is a child, update its parent to new head
        else:
            node.parent = Parent()
            node.parent.node = self._graph.nodes[msg["newHead"]]["node"]

        return node

    def update_no_head_orphan(self, ni, msg):
        node = self._graph.nodes[ni]["node"]
        node_state = node.state
        
        # if chdList is not empty, update the children state to state-1
        chdList = node.chdList
        if (len(chdList) > 0):
            for child in chdList:
                child_state = self._graph.nodes[child]["node"].state
                if(child_state.value - node_state.value > 1 and child_state != NodeType.CLUSTER_HEAD):
                    self._graph.nodes[child]["node"].state = NodeType(child_state.value - 1)

        return node

    # Observe if parent is still viable during election phase
    def observe_parent_potential(self, ni, Oth):
        node = self._graph.nodes[ni]["node"]
        # Check if parent overall score is greater than a threshold
        # print("pot: ", self._graph.nodes[ni]["node"].parent.overall_score)
      
        if node in self._destroyed or node.id == self._base_station:
            return None, None
        if(self._graph.nodes[ni]["node"].parent.worthiness_score > Oth): 
            return None, None

        # Parent is dead, move to closest CH
        closest_CH = self.find_closest_CH(node)
        # node.select_parent(self._graph.nodes[self._base_station]["node"])
        if(closest_CH == None):
            return None, None

        # Set parent to closest_CH
        node.parent = Parent()
        node.parent.node = closest_CH

        # Send REQUEST_PARENT message to new parent
        REQUEST_PARENT = {
            "child": node,
            "type": "REQUEST_PARENT"
        }

        return REQUEST_PARENT, closest_CH

    def find_closest_CH(self, node: Node):
        closest_CH = None
        nodeList = node.neighbourList
        if(node.state == NodeType.CLUSTER_HEAD):
            nodeList = node.broadcastList

        closest_CH = self.search_lists(node, nodeList)
        
        if(closest_CH == None and node.state == NodeType.CLUSTER_HEAD):
            closest_CH = self.search_lists(node, node.relayList)
            # if(closest_CH == None):
            #     closest_CH = self._graph.nodes[self._base_station]["node"]
        
        elif(closest_CH == None):
            node.state = NodeType.CLUSTER_HEAD
            closest_CH = self.search_lists(node, node.broadcastList)
            if(closest_CH == None):
                closest_CH = self.search_lists(node, node.relayList)
        
        if(closest_CH == None):
            closest_CH = self._graph.nodes[self._base_station]["node"]
        
        return closest_CH

    def search_lists(self, node: Node, list: list):
        closest_CH = None
        for neighbor, dist in list:
            if(neighbor.state == NodeType.CLUSTER_HEAD and node.parent.node != neighbor and \
                (neighbor.id not in node.chdList) and (closest_CH == None or closest_CH[1] > dist) and \
                (neighbor not in self._destroyed)):
                
                closest_CH = (neighbor, dist)
        
        if(closest_CH == None): return None

        return closest_CH[0]

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
        """Remove old delivered packets to avoid unbounded memory."""
        delivered = [p for p in self._packets if p.is_delivered]
        if len(delivered) > keep_last:
            remove_ids = {p.packet_id for p in delivered[:-keep_last]}
            self._packets = [p for p in self._packets
                             if p.packet_id not in remove_ids]


    # this is seeded randomness
    def randomizeBattery(self, seed):
        random.seed(seed)
        # cap the battery at 45%
        battery = [random.randint(45, 100) for _ in range(20)]

        for ni in self._graph.nodes:
            self._graph.nodes[ni]['node'].powerPercent = battery[ni]
            self._graph.nodes[ni]['node'].powerPercent =  self._graph.nodes[ni]['node'].power /(0.5e9)

    
    # Statistics Collection Functions

    def network_dead(self):
        # Amount of time it takes for the network to not work anymore
        return self._delivered_interval == 0

    def end_to_end_delay(self):
        # per-packet basis
        # time from packet transmission to BS
        # dist / speed
        # dist is from neighborList or broadcastList
        # or do I just time how long it takes each time? idk how i'd do that tho
        # what is the speed?
        pass

    def throughput(self):
        self._throughputs.append(self._received_packets_at_BS)
        self._received_packets_at_BS = 0

    def avg_throughput(self):
        # packets received at BS / time period (in ticks)
        if(len(self._throughputs) == 0): return 0
        return sum(self._throughputs) / (len(self._throughputs))
    
    def get_throughput_list(self):
        return self._throughputs
    

    # this is seeded randomness
def randomizeBattery(seed):
    random.seed(seed)
    # cap the battery at 45%
    return float(random.randint(15, 40))