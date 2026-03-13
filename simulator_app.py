"""
simulator_app.py — View / Controller Layer
============================================
Three-page GUI flow:
  Page 1 — Input node count and distance matrix
  Page 2 — Static network topology visualization
  Page 3 — Live packet simulation with Start / Pause / Stop

All network logic lives in NetworkModel.  This file only does:
  • tkinter layout and widget management   (View)
  • Reading user input and calling model   (Controller)
  • matplotlib rendering of model data     (View)
"""

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import networkx as nx

from network_model import NetworkModel, LayoutResult


# ──────────────────────────────────────────────
# Theme constants
# ──────────────────────────────────────────────
BG          = "#1e1e2e"
BG_DARK     = "#181825"
FG          = "#cdd6f4"
FG_DIM      = "#a6adc8"
ACCENT      = "#89b4fa"
ACCENT2     = "#a6e3a1"
WARN        = "#f9e2af"
ERR         = "#f38ba8"
ENTRY_BG    = "#313244"
BTN_BG      = "#45475a"
NODE_COLOR  = "#89b4fa"
BASE_COLOR  = "#f9e2af"
EDGE_COLOR  = "#585b70"
PKT_COLOR   = "#f38ba8"
PKT_DELIVER = "#a6e3a1"
FONT        = ("Segoe UI", 11)
FONT_BOLD   = ("Segoe UI", 12, "bold")
TITLE_FONT  = ("Segoe UI", 18, "bold")
MONO        = ("Consolas", 9)
MONO_SM     = ("Consolas", 8)

TICK_MS = 80          # milliseconds between simulation ticks


class WirelessSimulator(tk.Tk):

    def __init__(self) -> None:
        super().__init__()
        self.title("Wireless Network Simulator")
        self.geometry("960x700")
        self.configure(bg=BG)
        self.resizable(False, False)

        # ── Model ────────────────────────────
        self.model = NetworkModel()

        # ── View state ───────────────────────
        self.num_nodes: int = 0
        self.distance_entries: list[list[tk.Entry]] = []
        self._layout: LayoutResult | None = None

        # Simulation animation
        self._anim_id: str | None = None   # tkinter after() id
        self._running: bool = False
        self._log_lines: list[str] = []

        # ── Page container ───────────────────
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.show_page("input")

    # ─────────────────────────────────────────
    #  Navigation
    # ─────────────────────────────────────────
    def show_page(self, name: str) -> None:
        self._stop_animation()
        for w in self.container.winfo_children():
            w.destroy()

        builders = {
            "input":      self._build_input_page,
            "graph":      self._build_graph_page,
            "simulation": self._build_simulation_page,
        }
        builders[name]()

    # ═════════════════════════════════════════
    #  PAGE 1 — Input
    # ═════════════════════════════════════════
    def _build_input_page(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(frame, text="Step 1 — Define Nodes & Distances",
                 font=TITLE_FONT, bg=BG, fg=ACCENT).pack(anchor="w")
        tk.Label(
            frame,
            text="Enter the number of wireless nodes, then fill in "
                 "pairwise distances (meters).\n"
                 "Leave a cell as 0 or empty for no direct link.",
            font=FONT, bg=BG, fg=FG, justify="left",
        ).pack(anchor="w", pady=(4, 12))

        # Node count
        top = tk.Frame(frame, bg=BG)
        top.pack(anchor="w", pady=(0, 10))
        tk.Label(top, text="Number of nodes:", font=FONT_BOLD,
                 bg=BG, fg=FG).pack(side="left")
        self.node_var = tk.StringVar(value="4")
        tk.Spinbox(top, from_=2, to=12, width=4, textvariable=self.node_var,
                   font=FONT, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
                   insertbackground=FG, relief="flat").pack(side="left", padx=8)
        tk.Button(top, text="Generate Table", font=FONT_BOLD,
                  bg=ACCENT, fg="#11111b", activebackground=ACCENT2,
                  relief="flat", padx=14, pady=4,
                  command=self._generate_table).pack(side="left", padx=8)

        self.table_frame = tk.Frame(frame, bg=BG)
        self.table_frame.pack(fill="both", expand=True)

        nav = tk.Frame(frame, bg=BG)
        nav.pack(fill="x", pady=(10, 0))
        tk.Button(nav, text="Next  →  View Network Graph", font=FONT_BOLD,
                  bg=ACCENT2, fg="#11111b", activebackground=ACCENT,
                  relief="flat", padx=20, pady=6,
                  command=self._go_to_graph).pack(side="right")

    def _generate_table(self) -> None:
        for w in self.table_frame.winfo_children():
            w.destroy()
        try:
            n = int(self.node_var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid integer."); return
        if not 2 <= n <= 12:
            messagebox.showerror("Error", "Between 2 and 12."); return

        self.num_nodes = n
        self.distance_entries = []

        canvas = tk.Canvas(self.table_frame, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self.table_frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tk.Label(inner, text="", width=8, bg=BG).grid(row=0, column=0)
        for j in range(n):
            tk.Label(inner, text=f"Node {j+1}", font=FONT_BOLD,
                     bg=BG, fg=ACCENT, width=8).grid(row=0, column=j+1, padx=2, pady=2)

        _sample = {(0,1): "50", (0,2): "80", (0,3): "0",
                   (1,2): "60", (1,3): "90", (2,3): "45"}

        for i in range(n):
            tk.Label(inner, text=f"Node {i+1}", font=FONT_BOLD,
                     bg=BG, fg=ACCENT, width=8, anchor="e"
                     ).grid(row=i+1, column=0, padx=2, pady=2)
            row_e: list[tk.Entry] = []
            for j in range(n):
                e = tk.Entry(inner, width=8, font=FONT, justify="center",
                             bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat")
                e.grid(row=i+1, column=j+1, padx=2, pady=2)
                if i == j:
                    e.insert(0, "0")
                    e.configure(state="disabled", disabledbackground=BG_DARK,
                                disabledforeground="#585b70")
                elif n <= 5 and (min(i,j), max(i,j)) in _sample:
                    e.insert(0, _sample[(min(i,j), max(i,j))])
                row_e.append(e)
            self.distance_entries.append(row_e)

    def _read_distance_matrix(self) -> list[list[float]]:
        matrix = []
        for i in range(self.num_nodes):
            row = []
            for j in range(self.num_nodes):
                raw = self.distance_entries[i][j].get().strip()
                try:    row.append(float(raw) if raw else 0.0)
                except: row.append(0.0)
            matrix.append(row)
        return matrix

    def _go_to_graph(self) -> None:
        if self.num_nodes == 0 or not self.distance_entries:
            messagebox.showwarning("No data", "Generate the table first."); return
        matrix = self._read_distance_matrix()
        self.model.build_from_matrix(matrix)
        if not self.model.has_edges():
            messagebox.showwarning("No links", "Enter at least one positive distance."); return
        self._layout = self.model.compute_layout()
        self.show_page("graph")

    # ═════════════════════════════════════════
    #  PAGE 2 — Static Graph
    # ═════════════════════════════════════════
    def _build_graph_page(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(frame, text="Step 2 — Wireless Network Topology",
                 font=TITLE_FONT, bg=BG, fg=ACCENT).pack(anchor="w")

        stats = self.model.get_stats()
        conn = "fully connected" if stats.is_connected else f"{stats.num_components} component(s)"
        tk.Label(frame,
                 text=f"Nodes: {stats.num_nodes}    Edges: {stats.num_edges}    Topology: {conn}",
                 font=MONO, bg=BG, fg=FG_DIM).pack(anchor="w", pady=(4, 4))

        edge_str = "  ".join(f"({u}↔{v} {d['weight']:.0f}m)" for u, v, d in stats.edges)
        tk.Label(frame, text=f"Links: {edge_str}", font=MONO,
                 bg=BG, fg=FG_DIM, wraplength=900, justify="left"
                 ).pack(anchor="w", pady=(0, 4))

        fn_frame = tk.Frame(frame, bg=BG_DARK, relief="flat", bd=1)
        fn_frame.pack(fill="x", pady=(0, 6))
        tk.Label(fn_frame,
                 text="NetworkX:  " + " · ".join(self.model.nx_functions_used()),
                 font=MONO_SM, bg=BG_DARK, fg=ACCENT2,
                 wraplength=900, justify="left").pack(padx=8, pady=4)

        self._render_static_network(frame, self._layout)

        # Navigation — Back and Next
        nav = tk.Frame(frame, bg=BG)
        nav.pack(fill="x", pady=(6, 0))
        tk.Button(nav, text="←  Back to Input", font=FONT_BOLD,
                  bg=BTN_BG, fg=FG, activebackground=ACCENT,
                  relief="flat", padx=16, pady=6,
                  command=lambda: self.show_page("input")).pack(side="left")
        tk.Button(nav, text="Next  →  Packet Simulation", font=FONT_BOLD,
                  bg=ACCENT2, fg="#11111b", activebackground=ACCENT,
                  relief="flat", padx=20, pady=6,
                  command=lambda: self.show_page("simulation")).pack(side="right")

    def _render_static_network(self, parent: tk.Frame, layout: LayoutResult) -> None:
        G = self.model.graph
        fig = Figure(figsize=(9.0, 3.6), facecolor=BG)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG); ax.axis("off")
        ax.set_title("Wireless Network Topology", color=FG, fontsize=13,
                      fontweight="bold", pad=10)
        pos = layout.positions
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=EDGE_COLOR,
                               width=2, alpha=0.7)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=NODE_COLOR,
                               node_size=600, edgecolors="#11111b", linewidths=2)
        nx.draw_networkx_labels(G, pos, ax=ax, labels=layout.node_labels,
                                font_size=9, font_color="#11111b", font_weight="bold")
        nx.draw_networkx_edge_labels(
            G, pos, ax=ax, edge_labels=layout.edge_labels,
            font_size=8, font_color=ACCENT2,
            bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_DARK,
                      edgecolor=ACCENT2, alpha=0.8))
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # ═════════════════════════════════════════
    #  PAGE 3 — Live Packet Simulation
    # ═════════════════════════════════════════
    def _build_simulation_page(self) -> None:
        self.model.reset_simulation()
        self._log_lines.clear()

        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, padx=20, pady=12)

        # ── Title row ────────────────────────
        tk.Label(frame, text="Step 3 — Live Packet Simulation",
                 font=TITLE_FONT, bg=BG, fg=ACCENT).pack(anchor="w")
        tk.Label(frame,
                 text="Packets spawn at random nodes and travel hop-by-hop "
                      "to the base station via shortest path.",
                 font=FONT, bg=BG, fg=FG, justify="left"
                 ).pack(anchor="w", pady=(2, 6))

        # ── Base station selector ────────────
        cfg = tk.Frame(frame, bg=BG)
        cfg.pack(anchor="w", fill="x", pady=(0, 6))

        tk.Label(cfg, text="Base station:", font=FONT_BOLD,
                 bg=BG, fg=FG).pack(side="left")
        nodes = self.model.get_nodes()
        self._base_var = tk.StringVar(value=str(nodes[-1]))  # default: last node
        tk.OptionMenu(cfg, self._base_var, *[str(n) for n in nodes]).pack(side="left", padx=6)

        # ── Control buttons ──────────────────
        btn_frame = tk.Frame(cfg, bg=BG)
        btn_frame.pack(side="left", padx=20)

        self._btn_start = tk.Button(
            btn_frame, text="▶  Start", font=FONT_BOLD,
            bg=ACCENT2, fg="#11111b", activebackground=ACCENT,
            relief="flat", padx=14, pady=4, width=8,
            command=self._on_start)
        self._btn_start.pack(side="left", padx=4)

        self._btn_pause = tk.Button(
            btn_frame, text="⏸  Pause", font=FONT_BOLD,
            bg=WARN, fg="#11111b", activebackground=ACCENT,
            relief="flat", padx=14, pady=4, width=8,
            command=self._on_pause, state="disabled")
        self._btn_pause.pack(side="left", padx=4)

        self._btn_stop = tk.Button(
            btn_frame, text="⏹  Stop", font=FONT_BOLD,
            bg=ERR, fg="#11111b", activebackground=ACCENT,
            relief="flat", padx=14, pady=4, width=8,
            command=self._on_stop, state="disabled")
        self._btn_stop.pack(side="left", padx=4)

        # ── Stats bar ────────────────────────
        self._stats_var = tk.StringVar(value="Tick: 0  |  Active: 0  |  Delivered: 0")
        tk.Label(frame, textvariable=self._stats_var, font=MONO,
                 bg=BG_DARK, fg=ACCENT, anchor="w", padx=8, pady=4
                 ).pack(fill="x", pady=(0, 4))

        # ── Matplotlib canvas ────────────────
        self._sim_fig = Figure(figsize=(9.2, 3.4), facecolor=BG)
        self._sim_ax = self._sim_fig.add_subplot(111)
        self._sim_canvas = FigureCanvasTkAgg(self._sim_fig, master=frame)
        self._sim_canvas.get_tk_widget().pack(fill="both", expand=True)

        # ── Event log ────────────────────────
        log_frame = tk.Frame(frame, bg=BG_DARK, relief="flat", bd=1)
        log_frame.pack(fill="x", pady=(4, 4))
        self._log_text = tk.Text(
            log_frame, height=5, font=MONO_SM, bg=BG_DARK, fg=FG_DIM,
            relief="flat", wrap="word", state="disabled",
            insertbackground=FG, selectbackground=ACCENT,
        )
        log_sb = ttk.Scrollbar(log_frame, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_sb.set)
        self._log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        log_sb.pack(side="right", fill="y")

        # Navigation
        nav = tk.Frame(frame, bg=BG)
        nav.pack(fill="x", pady=(4, 0))
        tk.Button(nav, text="←  Back to Graph", font=FONT_BOLD,
                  bg=BTN_BG, fg=FG, activebackground=ACCENT,
                  relief="flat", padx=16, pady=6,
                  command=lambda: self.show_page("graph")).pack(side="left")

        # Initial render (static, no packets)
        self._draw_sim_frame()

    # ── Simulation controls ──────────────────
    def _on_start(self) -> None:
        base = int(self._base_var.get())
        self.model.set_base_station(base)

        if not self._running:
            # Fresh start or resume
            self._running = True
            self._btn_start.configure(state="disabled")
            self._btn_pause.configure(state="normal")
            self._btn_stop.configure(state="normal")
            self._tick_loop()

    def _on_pause(self) -> None:
        self._running = False
        self._stop_animation()
        self._btn_start.configure(state="normal", text="▶  Resume")
        self._btn_pause.configure(state="disabled")

    def _on_stop(self) -> None:
        self._running = False
        self._stop_animation()
        self.model.reset_simulation()
        self._log_lines.clear()
        self._stats_var.set("Tick: 0  |  Active: 0  |  Delivered: 0")
        self._btn_start.configure(state="normal", text="▶  Start")
        self._btn_pause.configure(state="disabled")
        self._btn_stop.configure(state="disabled")
        self._draw_sim_frame()
        self._append_log("[STOPPED]  Simulation reset.\n")

    def _stop_animation(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    # ── Animation loop ───────────────────────
    def _tick_loop(self) -> None:
        if not self._running:
            return

        snapshot = self.model.tick()
        self.model.purge_delivered()

        # Update stats bar
        self._stats_var.set(
            f"Tick: {snapshot.tick}  |  "
            f"Active: {snapshot.active_count}  |  "
            f"Delivered: {snapshot.delivered_count}"
        )

        # Append log events
        for line in snapshot.events:
            self._append_log(line + "\n")

        # Redraw
        self._draw_sim_frame()

        # Schedule next tick
        self._anim_id = self.after(TICK_MS, self._tick_loop)

    # ── Rendering ────────────────────────────
    def _draw_sim_frame(self) -> None:
        """Redraw the network + animated packets on the simulation canvas."""
        ax = self._sim_ax
        ax.clear()
        ax.set_facecolor(BG)
        ax.axis("off")

        G = self.model.graph
        layout = self._layout
        pos = layout.positions
        base = self.model.base_station

        # ── Edges ────────────────────────────
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=EDGE_COLOR,
                               width=2, alpha=0.5)

        # ── Nodes — base station highlighted ─
        regular = [n for n in G.nodes() if n != base]
        if regular:
            nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=regular,
                                   node_color=NODE_COLOR, node_size=500,
                                   edgecolors="#11111b", linewidths=2)
        nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=[base],
                               node_color=BASE_COLOR, node_size=700,
                               edgecolors="#11111b", linewidths=2.5,
                               node_shape="s")  # square = base station

        # ── Node labels ──────────────────────
        labels = dict(layout.node_labels)
        labels[base] = f"BS{base}"
        nx.draw_networkx_labels(G, pos, ax=ax, labels=labels,
                                font_size=8, font_color="#11111b", font_weight="bold")

        # ── Edge distance labels ─────────────
        nx.draw_networkx_edge_labels(
            G, pos, ax=ax, edge_labels=layout.edge_labels,
            font_size=7, font_color=ACCENT2,
            bbox=dict(boxstyle="round,pad=0.15", facecolor=BG_DARK,
                      edgecolor=ACCENT2, alpha=0.7))

        # ── Packets (animated dots) ──────────
        pkt_positions = self.model.get_packet_render_positions(layout)
        for px, py, pid, delivered in pkt_positions:
            color = PKT_DELIVER if delivered else PKT_COLOR
            size = 60 if delivered else 100
            ax.scatter(px, py, s=size, c=color, zorder=10,
                       edgecolors="#11111b", linewidths=1.0, alpha=0.9)
            ax.annotate(f"#{pid}", (px, py), fontsize=6,
                        color=FG, ha="center", va="bottom",
                        xytext=(0, 7), textcoords="offset points")

        self._sim_fig.tight_layout()
        self._sim_canvas.draw_idle()

    # ── Log helper ───────────────────────────
    def _append_log(self, text: str) -> None:
        self._log_text.configure(state="normal")
        self._log_text.insert("end", text)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")
        # Keep log bounded
        self._log_lines.append(text)
        if len(self._log_lines) > 200:
            self._log_lines = self._log_lines[-150:]
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.insert("end", "".join(self._log_lines))
            self._log_text.see("end")
            self._log_text.configure(state="disabled")


# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = WirelessSimulator()
    app.mainloop()