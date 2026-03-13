"""
simulator_app.py — View / Controller Layer
============================================
Handles all tkinter GUI, user interaction, and matplotlib rendering.
Delegates every network operation to NetworkModel (network_model.py).

Separation benefits:
  • The model can be tested with plain pytest — no window needed.
  • This file can be replaced with a PyQt / web / CLI front-end
    without changing a single line of network logic.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import networkx as nx

from network_model import NetworkModel


# ──────────────────────────────────────────────
# Theme constants (View-only concern)
# ──────────────────────────────────────────────
BG         = "#1e1e2e"
FG         = "#cdd6f4"
ACCENT     = "#89b4fa"
ACCENT2    = "#a6e3a1"
ENTRY_BG   = "#313244"
BTN_BG     = "#45475a"
NODE_COLOR = "#89b4fa"
EDGE_COLOR = "#585b70"
FONT       = ("Segoe UI", 11)
FONT_BOLD  = ("Segoe UI", 12, "bold")
TITLE_FONT = ("Segoe UI", 18, "bold")
MONO       = ("Consolas", 9)


class WirelessSimulator(tk.Tk):
    """
    Main application window.
    Acts as both View and Controller:
      • Builds / destroys UI pages          (View)
      • Reads user input, calls the model   (Controller)
      • Renders model results to the canvas (View)
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("Wireless Network Simulator")
        self.geometry("900x640")
        self.configure(bg=BG)
        self.resizable(False, False)

        # ── Model instance (the ONLY place network logic lives) ──
        self.model = NetworkModel()

        # ── View state ───────────────────────
        self.num_nodes: int = 0
        self.distance_entries: list[list[tk.Entry]] = []

        # ── Page container ───────────────────
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.show_page("input")

    # ─────────────────────────────────────────
    #  Page navigation
    # ─────────────────────────────────────────
    def show_page(self, name: str) -> None:
        for widget in self.container.winfo_children():
            widget.destroy()

        if name == "input":
            self._build_input_page()
        elif name == "graph":
            self._build_graph_page()

    # ═════════════════════════════════════════
    #  PAGE 1 — Node / Distance Input Table
    # ═════════════════════════════════════════
    def _build_input_page(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(
            frame, text="Step 1 — Define Nodes & Distances",
            font=TITLE_FONT, bg=BG, fg=ACCENT,
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=(
                "Enter the number of wireless nodes, then fill in "
                "pairwise distances (meters).\n"
                "Leave a cell as 0 or empty for no direct link."
            ),
            font=FONT, bg=BG, fg=FG, justify="left",
        ).pack(anchor="w", pady=(4, 12))

        # ── Node count selector ──────────────
        top = tk.Frame(frame, bg=BG)
        top.pack(anchor="w", pady=(0, 10))

        tk.Label(top, text="Number of nodes:", font=FONT_BOLD,
                 bg=BG, fg=FG).pack(side="left")

        self.node_var = tk.StringVar(value="4")
        tk.Spinbox(
            top, from_=2, to=12, width=4, textvariable=self.node_var,
            font=FONT, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
            insertbackground=FG, relief="flat",
        ).pack(side="left", padx=8)

        tk.Button(
            top, text="Generate Table", font=FONT_BOLD,
            bg=ACCENT, fg="#11111b", activebackground=ACCENT2,
            relief="flat", padx=14, pady=4,
            command=self._generate_table,
        ).pack(side="left", padx=8)

        # Table placeholder
        self.table_frame = tk.Frame(frame, bg=BG)
        self.table_frame.pack(fill="both", expand=True)

        # Navigation
        nav = tk.Frame(frame, bg=BG)
        nav.pack(fill="x", pady=(10, 0))
        tk.Button(
            nav, text="Next  →  View Network Graph", font=FONT_BOLD,
            bg=ACCENT2, fg="#11111b", activebackground=ACCENT,
            relief="flat", padx=20, pady=6,
            command=self._go_to_graph,
        ).pack(side="right")

    def _generate_table(self) -> None:
        """Create an N×N distance-matrix entry grid."""
        for w in self.table_frame.winfo_children():
            w.destroy()

        try:
            n = int(self.node_var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid integer for node count.")
            return
        if not 2 <= n <= 12:
            messagebox.showerror("Error", "Node count must be between 2 and 12.")
            return

        self.num_nodes = n
        self.distance_entries = []

        # Scrollable area
        canvas = tk.Canvas(self.table_frame, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical",
                                  command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Column headers
        tk.Label(inner, text="", width=8, bg=BG).grid(row=0, column=0)
        for j in range(n):
            tk.Label(inner, text=f"Node {j+1}", font=FONT_BOLD,
                     bg=BG, fg=ACCENT, width=8
                     ).grid(row=0, column=j + 1, padx=2, pady=2)

        # Sample data for small matrices
        _sample = {
            (0, 1): "50", (0, 2): "80", (0, 3): "0",
            (1, 2): "60", (1, 3): "90", (2, 3): "45",
        }

        for i in range(n):
            tk.Label(inner, text=f"Node {i+1}", font=FONT_BOLD,
                     bg=BG, fg=ACCENT, width=8, anchor="e"
                     ).grid(row=i + 1, column=0, padx=2, pady=2)
            row_entries: list[tk.Entry] = []
            for j in range(n):
                e = tk.Entry(inner, width=8, font=FONT, justify="center",
                             bg=ENTRY_BG, fg=FG, insertbackground=FG,
                             relief="flat")
                e.grid(row=i + 1, column=j + 1, padx=2, pady=2)

                if i == j:
                    e.insert(0, "0")
                    e.configure(state="disabled",
                                disabledbackground="#181825",
                                disabledforeground="#585b70")
                elif n <= 5:
                    key = (min(i, j), max(i, j))
                    if key in _sample:
                        e.insert(0, _sample[key])

                row_entries.append(e)
            self.distance_entries.append(row_entries)

    # ── Controller: read UI → feed model ─────
    def _read_distance_matrix(self) -> list[list[float]]:
        """
        Extract the distance matrix from the entry widgets.
        Pure data extraction — returns a plain list-of-lists
        that the model can consume directly.
        """
        n = self.num_nodes
        matrix: list[list[float]] = []
        for i in range(n):
            row: list[float] = []
            for j in range(n):
                raw = self.distance_entries[i][j].get().strip()
                try:
                    row.append(float(raw) if raw else 0.0)
                except ValueError:
                    row.append(0.0)
            matrix.append(row)
        return matrix

    def _go_to_graph(self) -> None:
        if self.num_nodes == 0 or not self.distance_entries:
            messagebox.showwarning(
                "No data",
                "Please generate the table and fill in distances first.",
            )
            return

        # ── Controller action: build model from UI data ──
        matrix = self._read_distance_matrix()
        self.model.build_from_matrix(matrix)

        if not self.model.has_edges():
            messagebox.showwarning(
                "No links",
                "All distances are 0 or empty — enter at least one "
                "positive distance to create a wireless link.",
            )
            return

        self.show_page("graph")

    # ═════════════════════════════════════════
    #  PAGE 2 — Network Graph Visualization
    # ═════════════════════════════════════════
    def _build_graph_page(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(
            frame, text="Step 2 — Wireless Network Topology",
            font=TITLE_FONT, bg=BG, fg=ACCENT,
        ).pack(anchor="w")

        # ── Ask the MODEL for stats (no nx calls here) ──
        stats = self.model.get_stats()
        conn_label = (
            "fully connected" if stats.is_connected
            else f"{stats.num_components} separate component(s)"
        )
        info_text = (
            f"Nodes: {stats.num_nodes}    "
            f"Edges: {stats.num_edges}    "
            f"Topology: {conn_label}"
        )
        tk.Label(frame, text=info_text, font=MONO, bg=BG, fg="#a6adc8",
                 wraplength=840, justify="left"
                 ).pack(anchor="w", pady=(4, 4))

        # Connection detail
        edge_str = "  ".join(
            f"({u}↔{v} {d['weight']:.0f}m)" for u, v, d in stats.edges
        )
        tk.Label(frame, text=f"Links: {edge_str}", font=MONO,
                 bg=BG, fg="#a6adc8", wraplength=840, justify="left"
                 ).pack(anchor="w", pady=(0, 4))

        # ── NetworkX functions panel ─────────
        fn_frame = tk.Frame(frame, bg="#181825", relief="flat", bd=1)
        fn_frame.pack(fill="x", pady=(0, 8))
        fn_list = " · ".join(self.model.nx_functions_used())
        tk.Label(
            fn_frame,
            text=f"NetworkX functions available:  {fn_list}",
            font=MONO, bg="#181825", fg=ACCENT2,
            wraplength=840, justify="left",
        ).pack(padx=8, pady=6)

        # ── Ask the MODEL for layout data ────
        layout = self.model.compute_layout()

        # ── Render with matplotlib (View-only) ──
        self._render_network(frame, layout)

        # Navigation
        self._add_back_button(frame)

    def _render_network(self, parent: tk.Frame, layout) -> None:
        """
        Pure rendering method.  Takes pre-computed positions and labels
        from the model and draws them — the View never calls NetworkX
        graph-building functions.
        """
        G = self.model.graph  # read-only access for draw_networkx_*

        fig = Figure(figsize=(8.4, 3.9), facecolor=BG)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG)
        ax.set_title("Wireless Network Topology",
                      color=FG, fontsize=13, fontweight="bold", pad=10)
        ax.axis("off")

        pos = layout.positions

        # Draw edges
        nx.draw_networkx_edges(
            G, pos, ax=ax,
            edge_color=EDGE_COLOR, width=2, style="solid", alpha=0.7,
        )

        # Draw nodes
        nx.draw_networkx_nodes(
            G, pos, ax=ax,
            node_color=NODE_COLOR, node_size=600,
            edgecolors="#11111b", linewidths=2,
        )

        # Draw node labels
        nx.draw_networkx_labels(
            G, pos, ax=ax,
            labels=layout.node_labels,
            font_size=9, font_color="#11111b", font_weight="bold",
        )

        # Draw edge labels (distances)
        nx.draw_networkx_edge_labels(
            G, pos, ax=ax,
            edge_labels=layout.edge_labels,
            font_size=8, font_color=ACCENT2,
            bbox=dict(boxstyle="round,pad=0.2",
                      facecolor="#181825", edgecolor=ACCENT2, alpha=0.8),
        )

        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # ── Shared UI helper ─────────────────────
    def _add_back_button(self, parent: tk.Frame) -> None:
        nav = tk.Frame(parent, bg=BG)
        nav.pack(fill="x", pady=(8, 0))
        tk.Button(
            nav, text="←  Back to Input", font=FONT_BOLD,
            bg=BTN_BG, fg=FG, activebackground=ACCENT,
            relief="flat", padx=16, pady=6,
            command=lambda: self.show_page("input"),
        ).pack(side="left")


# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = WirelessSimulator()
    app.mainloop()