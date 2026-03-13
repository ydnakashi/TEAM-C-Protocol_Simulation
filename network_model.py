"""
network_model.py — Model Layer
===============================
Owns the NetworkX graph and every network-related operation.
Has ZERO knowledge of tkinter, matplotlib, or any GUI framework.

This separation means you can:
  • Unit-test graph logic without launching a window
  • Swap the GUI (e.g. move to PyQt or a web frontend) without touching this file
  • Add simulation features (routing, signal propagation) in one place

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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx


# ──────────────────────────────────────────────
#  Data classes for clean return types
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


# ──────────────────────────────────────────────
#  The Model
# ──────────────────────────────────────────────
class NetworkModel:
    """
    Encapsulates a wireless network as a NetworkX undirected graph.
    Every public method is a pure network operation — no UI code.
    """

    def __init__(self) -> None:
        self._graph: nx.Graph = nx.Graph()          # ★ nx.Graph()

    # ── Property access ──────────────────────
    @property
    def graph(self) -> nx.Graph:
        """Direct access when advanced callers need the raw graph."""
        return self._graph

    # ── Build / mutate ───────────────────────
    def build_from_matrix(self, matrix: list[list[float]]) -> None:
        """
        Construct the network from an N×N distance matrix.
        Clears any previous graph state first.

        Args:
            matrix: Square list-of-lists where matrix[i][j] is the
                    distance between node i+1 and node j+1.
                    A value of 0 means "no direct link".
        """
        self._graph.clear()                          # ★ G.clear()

        n = len(matrix)

        for i in range(n):
            self._graph.add_node(                    # ★ G.add_node()
                i + 1,
                label=f"Node {i + 1}",
            )

        for i in range(n):
            for j in range(i + 1, n):
                dist = matrix[i][j]
                if dist > 0:
                    self._graph.add_edge(            # ★ G.add_edge()
                        i + 1, j + 1,
                        weight=dist,
                    )

    def add_node(self, node_id: int, **attrs: Any) -> None:
        """Add a single node (useful for future dynamic simulation)."""
        self._graph.add_node(node_id, **attrs)       # ★ G.add_node()

    def remove_node(self, node_id: int) -> None:
        """Remove a node and all its incident edges."""
        self._graph.remove_node(node_id)             # ★ G.remove_node()

    def add_edge(self, u: int, v: int, weight: float) -> None:
        """Add or update a weighted edge."""
        self._graph.add_edge(u, v, weight=weight)    # ★ G.add_edge()

    def remove_edge(self, u: int, v: int) -> None:
        """Remove a specific edge."""
        self._graph.remove_edge(u, v)                # ★ G.remove_edge()

    # ── Query ────────────────────────────────
    def get_stats(self) -> NetworkStats:
        """Return a snapshot of network-level metrics."""
        G = self._graph
        nodes_exist = G.number_of_nodes() > 0        # ★ G.number_of_nodes()
        return NetworkStats(
            num_nodes=G.number_of_nodes(),
            num_edges=G.number_of_edges(),            # ★ G.number_of_edges()
            is_connected=nx.is_connected(G) if nodes_exist else False,  # ★ nx.is_connected()
            num_components=nx.number_connected_components(G) if nodes_exist else 0,  # ★ nx.connected_components()
            edges=list(G.edges(data=True)),           # ★ G.edges(data=True)
        )

    def has_edges(self) -> bool:
        return self._graph.number_of_edges() > 0

    def get_nodes(self) -> list[int]:
        """Return sorted list of node IDs."""
        return sorted(self._graph.nodes())            # ★ G.nodes()

    def get_neighbors(self, node_id: int) -> list[int]:
        """Return neighbors of a given node."""
        return list(self._graph.neighbors(node_id))   # ★ G.neighbors()

    def get_degree(self, node_id: int) -> int:
        """Return the degree (number of connections) of a node."""
        return self._graph.degree(node_id)            # ★ G.degree()

    def get_shortest_path(self, source: int, target: int) -> list[int]:
        """Return the shortest hop-count path between two nodes."""
        return nx.shortest_path(                      # ★ nx.shortest_path()
            self._graph, source=source, target=target,
        )

    def get_shortest_path_length(self, source: int, target: int) -> int:
        """Return the hop-count distance between two nodes."""
        return nx.shortest_path_length(               # ★ nx.shortest_path_length()
            self._graph, source=source, target=target,
        )

    # ── Layout (renderer-agnostic) ───────────
    def compute_layout(self, seed: int = 42) -> LayoutResult:
        """
        Compute node positions and formatted labels for rendering.
        Returns plain dicts — the caller decides how to draw them.
        """
        G = self._graph
        n = G.number_of_nodes()

        # ★ nx.spring_layout() — Fruchterman-Reingold force-directed
        positions = nx.spring_layout(G, seed=seed, k=2.5 / (n ** 0.5))

        # Node labels
        node_labels = {node: f"N{node}" for node in G.nodes()}  # ★ G.nodes()

        # ★ nx.get_edge_attributes() — retrieve all weights at once
        raw_weights = nx.get_edge_attributes(G, "weight")
        edge_labels = {k: f"{v:.0f} m" for k, v in raw_weights.items()}

        return LayoutResult(
            positions=positions,
            node_labels=node_labels,
            edge_labels=edge_labels,
        )

    # ── Utility / summary ────────────────────
    def summary(self) -> str:
        """Human-readable one-liner for status bars / logs."""
        s = self.get_stats()
        conn = "connected" if s.is_connected else f"{s.num_components} components"
        return (
            f"Nodes: {s.num_nodes}  |  Edges: {s.num_edges}  |  {conn}"
        )

    def nx_functions_used(self) -> list[str]:
        """Return the list of NetworkX functions this model exercises."""
        return [
            "nx.Graph()",
            "G.add_node()",
            "G.add_edge()",
            "G.remove_node()",
            "G.remove_edge()",
            "G.clear()",
            "G.nodes()",
            "G.edges(data=True)",
            "G.number_of_nodes()",
            "G.number_of_edges()",
            "G.degree()",
            "G.neighbors()",
            "nx.spring_layout()",
            "nx.get_edge_attributes()",
            "nx.is_connected()",
            "nx.connected_components()",
            "nx.shortest_path()",
            "nx.shortest_path_length()",
        ]