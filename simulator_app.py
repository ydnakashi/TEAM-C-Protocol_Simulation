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
        self.geometry("1500x1000")
        self.configure(bg=BG)
        self.resizable(True, True)

        # ── Model ────────────────────────────
        self.model = NetworkModel()

        # ── View state ───────────────────────
        self.num_nodes: int = 0
        self.distance_entries: list[list[tk.Entry]] = []
        self._grid_coords: list[tuple[float, float]] = []
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

        tk.Label(frame, text="Step 1 — Define Grid & Node Positions",
                 font=TITLE_FONT, bg=BG, fg=ACCENT).pack(anchor="w")
        tk.Label(
            frame,
            text="Set M × N grid dimensions to place nodes on a grid.\n"
                 "Edit coordinates in the right panel, then click Update Preview to adjust.",
            font=FONT, bg=BG, fg=FG, justify="left",
        ).pack(anchor="w", pady=(4, 8))

        # ── Controls ─────────────────────────
        top = tk.Frame(frame, bg=BG)
        top.pack(anchor="w", pady=(0, 8))

        tk.Label(top, text="Rows (M):", font=FONT_BOLD, bg=BG, fg=FG).pack(side="left")
        self.rows_var = tk.StringVar(value="3")
        tk.Spinbox(top, from_=1, to=20, width=3, textvariable=self.rows_var,
                   font=FONT, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
                   insertbackground=FG, relief="flat").pack(side="left", padx=(4, 12))

        tk.Label(top, text="Cols (N):", font=FONT_BOLD, bg=BG, fg=FG).pack(side="left")
        self.cols_var = tk.StringVar(value="3")
        tk.Spinbox(top, from_=1, to=30, width=3, textvariable=self.cols_var,
                   font=FONT, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
                   insertbackground=FG, relief="flat").pack(side="left", padx=(4, 12))

        tk.Label(top, text="Link Range:", font=FONT_BOLD, bg=BG, fg=FG).pack(side="left")
        self.range_var = tk.StringVar(value="1.5")
        tk.Spinbox(top, from_=0.5, to=50.0, increment=0.5, width=5,
                   textvariable=self.range_var,
                   font=FONT, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
                   insertbackground=FG, relief="flat").pack(side="left", padx=(4, 12))

        tk.Button(top, text="Generate Grid", font=FONT_BOLD,
                  bg=ACCENT, fg="#11111b", activebackground=ACCENT2,
                  relief="flat", padx=14, pady=4,
                  command=self._generate_grid).pack(side="left")

        # ── Two-panel content ────────────────
        content = tk.Frame(frame, bg=BG)
        content.pack(fill="both", expand=True)

        # Left: grid preview (matplotlib canvas)
        self.grid_canvas_frame = tk.Frame(content, bg=BG_DARK)
        self.grid_canvas_frame.pack(side="left", fill="both", expand=True)

        # Right: coordinate text editor
        right = tk.Frame(content, bg=BG, width=280)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(right, text="Node Coordinates", font=FONT_BOLD,
                 bg=BG, fg=ACCENT).pack(anchor="w")
        tk.Label(right, text="One per line:  x, y", font=MONO,
                 bg=BG, fg=FG_DIM).pack(anchor="w", pady=(2, 4))

        text_frame = tk.Frame(right, bg=BG_DARK)
        text_frame.pack(fill="both", expand=True)
        coord_sb_y = ttk.Scrollbar(text_frame, orient="vertical")
        coord_sb_x = ttk.Scrollbar(text_frame, orient="horizontal")
        self.coord_text = tk.Text(
            text_frame, font=MONO, bg=ENTRY_BG, fg=FG,
            insertbackground=FG, relief="flat", wrap="none",
            yscrollcommand=coord_sb_y.set, xscrollcommand=coord_sb_x.set,
        )
        coord_sb_y.configure(command=self.coord_text.yview)
        coord_sb_x.configure(command=self.coord_text.xview)
        coord_sb_y.pack(side="right", fill="y")
        coord_sb_x.pack(side="bottom", fill="x")
        self.coord_text.pack(fill="both", expand=True, padx=2, pady=2)

        tk.Button(right, text="↺  Update Preview", font=FONT_BOLD,
                  bg=BTN_BG, fg=FG, activebackground=ACCENT,
                  relief="flat", padx=10, pady=4,
                  command=self._update_grid_preview).pack(fill="x", pady=(6, 0))

        # ── Navigation ───────────────────────
        nav = tk.Frame(frame, bg=BG)
        nav.pack(fill="x", pady=(10, 0))
        tk.Button(nav, text="Next  →  View Network Graph", font=FONT_BOLD,
                  bg=ACCENT2, fg="#11111b", activebackground=ACCENT,
                  relief="flat", padx=20, pady=6,
                  command=self._go_to_graph).pack(side="right")

        # Auto-generate on first load
        self._generate_grid()

    def _generate_grid(self) -> None:
        try:
            m = int(self.rows_var.get())
            n = int(self.cols_var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter valid integers for M and N."); return
        if not (1 <= m <= 10 and 1 <= n <= 10):
            messagebox.showerror("Error", "M and N must each be between 1 and 10."); return
        if m * n < 2:
            messagebox.showerror("Error", "Grid must have at least 2 nodes (M × N ≥ 2)."); return

        # Row-major order; (0,0) top-left, x increases right, y increases downward
        coords: list[tuple[float, float]] = [
            (float(col), float(row))
            for row in range(m) for col in range(n)
        ]
        self.num_nodes = len(coords)
        self._grid_coords = coords

        self.coord_text.delete("1.0", "end")
        for x, y in coords:
            self.coord_text.insert("end", f"{x:.0f}, {y:.0f}\n")

        self._draw_grid_canvas(coords)

    def _draw_grid_canvas(self, coords: list[tuple[float, float]]) -> None:
        for w in self.grid_canvas_frame.winfo_children():
            w.destroy()

        fig = Figure(figsize=(5.5, 4.5), facecolor=BG)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG)
        ax.set_title("Node Layout Preview", color=FG, fontsize=11, pad=8)
        ax.set_xlabel("X", color=FG_DIM, fontsize=9)
        ax.set_ylabel("Y", color=FG_DIM, fontsize=9)
        ax.tick_params(axis="both", colors=FG_DIM, labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(BTN_BG)
        ax.grid(True, color=BTN_BG, alpha=0.5, linewidth=0.8)
        ax.set_axisbelow(True)

        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            ax.scatter(xs, ys, s=350, c=NODE_COLOR, zorder=5,
                       edgecolors="#11111b", linewidths=1.5)
            for i, (x, y) in enumerate(coords):
                ax.annotate(f"N{i+1}", (x, y), fontsize=8,
                            color="#11111b", ha="center", va="center",
                            fontweight="bold", zorder=6)

            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            xpad = max((xmax - xmin) * 0.25, 0.5)
            ypad = max((ymax - ymin) * 0.25, 0.5)
            ax.set_xlim(xmin - xpad, xmax + xpad)
            ax.set_ylim(ymax + ypad, ymin - ypad)  # invert: 0 at top, increases downward

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.grid_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _update_grid_preview(self) -> None:
        coords = self._parse_coordinate_text()
        if coords is None:
            return
        self._grid_coords = coords
        self.num_nodes = len(coords)
        self._draw_grid_canvas(coords)

    def _parse_coordinate_text(self) -> list[tuple[float, float]] | None:
        raw = self.coord_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("No data", "Enter at least two coordinates."); return None
        coords: list[tuple[float, float]] = []
        for i, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 2:
                messagebox.showerror("Parse error",
                    f"Line {i}: expected  x, y  — got: {line!r}"); return None
            try:
                x, y = float(parts[0]), float(parts[1])
            except ValueError:
                messagebox.showerror("Parse error",
                    f"Line {i}: non-numeric value: {line!r}"); return None
            coords.append((x, y))
        if len(coords) < 2:
            messagebox.showwarning("Too few nodes",
                "Enter at least 2 node coordinates."); return None
        return coords

    def _go_to_graph(self) -> None:
        coords = self._parse_coordinate_text()
        if coords is None:
            return
        try:
            link_range = float(self.range_var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid link range."); return
        self._grid_coords = coords
        self.num_nodes = len(coords)
        self.model.build_from_coordinates(coords, link_range)
        if not self.model.has_edges():
            messagebox.showwarning(
                "No links",
                "No nodes are within link range of each other.\n"
                "Try increasing the Link Range value.",
            ); return
        self._layout = self.model.compute_layout_from_coords(coords)
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

        print("size ", G.size)
        fig = Figure(figsize=(9.0, 3.6), facecolor=BG)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG); ax.axis("off")
        ax.set_title("Wireless Network Topology", color=FG, fontsize=13,
                      fontweight="bold", pad=10)
        pos = layout.positions
        # nx.draw_networkx_edges(G, pos, ax=ax, edge_color=EDGE_COLOR,
        #                        width=2, alpha=0.7)
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