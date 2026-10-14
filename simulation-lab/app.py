"""Simulation Lab desktop application; rendering stays inside its own window."""
import argparse
from dataclasses import fields
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from core import Camera, Settings, Simulation, Vec3, follow_target, fov_radius, project, select_target

VERSION = "1.0.0"


def resource_path(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


class App:
    def __init__(self, root, directory):
        self.root = root
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=self.directory / "application.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s", force=True)
        self.config_path = self.directory / "settings.json"
        self.load_warning = None
        try:
            self.settings = Settings.load(self.config_path) if self.config_path.exists() else Settings()
        except (ValueError, OSError) as error:
            logging.warning("Settings rejected: %s", error)
            self.settings = Settings()
            self.load_warning = str(error)
            # Preserve rejected input for diagnosis before subsequent saves.
            try:
                self.config_path.replace(self.directory / ("settings-invalid-%d.json" % time.time_ns()))
            except OSError:
                logging.exception("Could not preserve invalid settings")
        self.camera = Camera(Vec3(0, 0, 1.6))
        self.sim = Simulation(self.settings.player_count)
        self.paused = False
        self.keys = set()
        self.last_drag = None
        self.save_job = None
        self.frame_job = None
        self.last_time = time.perf_counter()
        self.target = None
        self.fps = 60.0
        self.profile = json.loads(resource_path("profiles/fortnite-14.60.json").read_text(encoding="utf-8"))
        root.title("Simulation Lab %s — SIMULATED PLAYERS" % VERSION)
        root.geometry("1280x800")
        root.minsize(1000, 700)
        root.configure(bg="#101824")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.callback_error
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#172233")
        style.configure("TLabel", background="#172233", foreground="#e1e9f4")
        style.configure("TCheckbutton", background="#172233", foreground="#e1e9f4")
        style.configure("TButton", padding=6)
        style.configure("TLabelframe", background="#172233")
        style.configure("TLabelframe.Label", background="#172233", foreground="#7bc8ff")
        header = tk.Frame(root, bg="#101824")
        header.pack(fill="x", padx=18, pady=12)
        tk.Label(header, text="SIMULATION LAB", font=("Segoe UI", 18, "bold"), bg="#101824", fg="#e1e9f4").pack(side="left")
        tk.Label(header, text="Standalone simulation • Fortnite 14.60 integration unavailable",
                 bg="#101824", fg="#ffcb7c", font=("Segoe UI", 10)).pack(side="right")
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=18)
        self.canvas = tk.Canvas(body, bg="#0c1420", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.panel = ttk.Frame(body, width=290, padding=12)
        self.panel.pack(side="right", fill="y")
        self.panel.pack_propagate(False)
        self.variables = {}
        notebook = ttk.Notebook(self.panel)
        notebook.pack(fill="x", pady=(0, 12))
        visual = ttk.Frame(notebook, padding=8)
        notebook.add(visual, text="Visuals")
        for name, text in [("boxes", "Bounding boxes"), ("skeletons", "Skeletons"),
                           ("labels", "Names / distance"), ("health_bars", "Health bars"),
                           ("tracers", "Tracers"), ("show_fov", "Selection FOV circle")]:
            self.checkbox(visual, name, text)
        target = ttk.Frame(notebook, padding=8)
        notebook.add(target, text="Targets")
        for name, text in [("visible_only", "Visible targets only"), ("include_teammates", "Include teammates"),
                           ("follow", "Follow with simulation camera")]:
            self.checkbox(target, name, text)
        self.combo(target, "selection", ["Crosshair", "Distance", "Health"])
        self.combo(target, "aim_point", ["Head", "Chest"])
        self.slider(target, "selection_fov", "Selection FOV (full angle)", 2, 80)
        self.slider(target, "smoothness", "Smoothing time (seconds)", .02, 2)
        self.slider(target, "max_distance", "Maximum distance (meters)", 10, 200)
        scene = ttk.Frame(notebook, padding=8)
        notebook.add(scene, text="Scene")
        self.slider(scene, "camera_fov", "Camera horizontal FOV", 40, 120)
        self.slider(scene, "player_count", "Player count", 1, 64)
        self.slider(scene, "speed", "Simulation speed", 0, 3)
        actions = ttk.Frame(self.panel)
        actions.pack(fill="x")
        self.pause_button = ttk.Button(actions, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Reset scene", command=self.reset_scene).pack(side="left", fill="x", expand=True)
        ttk.Button(self.panel, text="Restore default settings", command=self.defaults).pack(fill="x", pady=6)
        ttk.Button(self.panel, text="Profile / tester help", command=self.help).pack(fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.panel, textvariable=self.status, wraplength=260).pack(fill="x", pady=8)
        footer = tk.Label(root, text="Click scene to focus • WASD move • Q/E vertical • Drag to look • Space pause • R reset • Esc release keys",
                          bg="#101824", fg="#a6b5cb", pady=10)
        footer.pack(fill="x")
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda event: setattr(self, "last_drag", None))
        self.canvas.bind("<KeyPress>", self.key_down)
        self.canvas.bind("<KeyRelease>", lambda event: self.keys.discard(event.keysym.lower()))
        root.bind("<FocusOut>", lambda event: self.keys.clear())
        root.bind("<Escape>", lambda event: self.keys.clear())
        if self.load_warning:
            root.after(50, lambda: messagebox.showwarning("Settings reset", self.load_warning, parent=root))
        self.tick()

    def callback_error(self, kind, error, traceback):
        logging.error("UI error", exc_info=(kind, error, traceback))
        messagebox.showerror("Application error", "%s\nSee %s" % (error, self.directory / "application.log"), parent=self.root)

    def checkbox(self, parent, name, text):
        variable = tk.BooleanVar(value=getattr(self.settings, name))
        self.variables[name] = variable
        ttk.Checkbutton(parent, text=text, variable=variable, command=lambda: self.changed(name)).pack(anchor="w")

    def combo(self, parent, name, values):
        variable = tk.StringVar(value=getattr(self.settings, name))
        self.variables[name] = variable
        widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=24)
        widget.pack(fill="x", pady=3)
        widget.bind("<<ComboboxSelected>>", lambda event: self.changed(name))

    def slider(self, parent, name, label, low, high):
        variable = tk.DoubleVar(value=getattr(self.settings, name))
        self.variables[name] = variable
        text = tk.StringVar()
        def update(value=None):
            number = round(variable.get()) if name == "player_count" else variable.get()
            text.set("%s: %.2f" % (label, number))
            self.changed(name)
        ttk.Label(parent, textvariable=text).pack(anchor="w")
        ttk.Scale(parent, from_=low, to=high, variable=variable, command=update).pack(fill="x")
        variable.trace_add("write", lambda *args: text.set("%s: %.2f" % (label, variable.get())))
        text.set("%s: %.2f" % (label, variable.get()))

    def changed(self, name):
        value = self.variables[name].get()
        if name == "player_count":
            value = round(value)
        setattr(self.settings, name, value)
        if name == "player_count" and len(self.sim.players) != value:
            self.sim = Simulation(value)
        if self.save_job:
            self.root.after_cancel(self.save_job)
        self.save_job = self.root.after(400, self.save)

    def save(self):
        self.save_job = None
        try:
            self.settings.save(self.config_path)
            self.status.set("Settings saved automatically")
        except OSError as error:
            logging.exception("Save failed")
            self.status.set("Settings could not be saved: " + str(error))

    def defaults(self):
        self.settings = Settings()
        for name, variable in self.variables.items():
            variable.set(getattr(self.settings, name))
        self.reset_scene()
        self.save()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.configure(text="Resume" if self.paused else "Pause")

    def reset_scene(self):
        self.sim = Simulation(self.settings.player_count)
        self.camera = Camera(Vec3(0, 0, 1.6))
        self.target = None
        self.keys.clear()

    def drag_start(self, event):
        self.canvas.focus_set()
        self.last_drag = (event.x, event.y)

    def drag(self, event):
        if self.last_drag:
            self.camera.yaw = (self.camera.yaw + (event.x - self.last_drag[0]) * .18 + 180) % 360 - 180
            self.camera.pitch = max(-85, min(85, self.camera.pitch - (event.y - self.last_drag[1]) * .18))
        self.last_drag = (event.x, event.y)

    def key_down(self, event):
        key = event.keysym.lower()
        if key not in self.keys:
            if key == "space":
                self.toggle_pause()
            elif key == "r":
                self.reset_scene()
        self.keys.add(key)

    def tick(self):
        now = time.perf_counter()
        elapsed = now - self.last_time
        dt = min(.05, max(0, elapsed))
        self.last_time = now
        self.fps = .92 * self.fps + .08 / max(.001, elapsed)
        if not self.paused:
            self.sim.update(dt * self.settings.speed)
        yaw = math.radians(self.camera.yaw)
        forward = int("w" in self.keys) - int("s" in self.keys)
        right = int("d" in self.keys) - int("a" in self.keys)
        self.camera.position.x += (math.cos(yaw) * forward - math.sin(yaw) * right) * dt * 10
        self.camera.position.y += (math.sin(yaw) * forward + math.cos(yaw) * right) * dt * 10
        self.camera.position.z += (int("e" in self.keys) - int("q" in self.keys)) * dt * 5
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        self.target = select_target(self.sim.players, self.sim.time, self.camera, width, height, self.settings)
        if self.settings.follow and self.target and not self.last_drag:
            follow_target(self.camera, self.target.point(self.sim.time, self.settings.aim_point), dt, self.settings.smoothness)
        self.draw(width, height)
        self.frame_job = self.root.after(16, self.tick)

    def screen(self, point, width, height):
        return project(point, self.camera, width, height, self.settings.camera_fov)

    def draw(self, width, height):
        canvas = self.canvas
        canvas.delete("all")
        for x in range(10, 101, 10):
            for y in range(-50, 51, 10):
                point = self.screen(Vec3(x, y, 0), width, height)
                if point and 0 <= point[0] <= width and 0 <= point[1] <= height:
                    canvas.create_oval(point[0]-1, point[1]-1, point[0]+1, point[1]+1, fill="#2a3d50", outline="")
        # Far actors are painted first so nearer silhouettes cover them.
        players = sorted(self.sim.players, key=lambda p: (p.position(self.sim.time) - self.camera.position).length(), reverse=True)
        rendered = 0
        for player in players:
            position = player.position(self.sim.time)
            distance = (position - self.camera.position).length()
            if distance > self.settings.max_distance:
                continue
            top = self.screen(Vec3(position.x, position.y, 1.9), width, height)
            feet = self.screen(position, width, height)
            if not top or not feet:
                continue
            h = feet[1] - top[1]
            if h < 2 or h > height * 8:
                continue
            center = (top[0] + feet[0]) / 2
            left, right, bottom = center - h * .22, center + h * .22, feet[1]
            if right < 0 or left > width or bottom < 0 or top[1] > height:
                continue
            rendered += 1
            color = "#ffd166" if self.target and player.id == self.target.id else ("#74b9ff" if player.teammate else "#f17891")
            if not player.visible:
                color = "#748095"
            # The underlying synthetic actor remains visible when annotations are off.
            canvas.create_oval(center-h*.075, top[1], center+h*.075, top[1]+h*.15, fill="#364960", outline="")
            canvas.create_polygon(center-h*.10, top[1]+h*.18, center+h*.10, top[1]+h*.18,
                                  center+h*.14, bottom, center-h*.14, bottom, fill="#243449")
            if self.settings.boxes:
                canvas.create_rectangle(left, top[1], right, bottom, outline=color, width=2)
            if self.settings.skeletons:
                # Synthetic articulated joints, not a game skeleton definition.
                joints = {"head": (0, 1.72), "neck": (0, 1.5), "hip": (0, .9),
                          "ls": (-.24, 1.45), "rs": (.24, 1.45), "lh": (-.4, 1.05), "rh": (.4, 1.05),
                          "lk": (-.14, .48), "rk": (.14, .48), "lf": (-.18, 0), "rf": (.18, 0)}
                points = {name: self.screen(Vec3(position.x, position.y + offset, z), width, height)
                          for name, (offset, z) in joints.items()}
                for a, b in [("head", "neck"), ("neck", "hip"), ("ls", "rs"), ("ls", "lh"),
                             ("rs", "rh"), ("hip", "lk"), ("hip", "rk"), ("lk", "lf"), ("rk", "rf")]:
                    if points[a] and points[b]:
                        canvas.create_line(*points[a], *points[b], fill=color, width=2)
            if self.settings.labels:
                canvas.create_text(center, top[1]-10, text="%s %02d · %.0fm%s" % ("Ally" if player.teammate else "Player", player.id, distance,
                                       " · occluded" if not player.visible else ""), fill=color, font=("Segoe UI", 9))
            if self.settings.health_bars:
                canvas.create_rectangle(left-7, top[1], left-3, bottom, fill="#243449", outline="")
                canvas.create_rectangle(left-7, bottom-h*player.health/100, left-3, bottom, fill="#63d5a4", outline="")
            if self.settings.tracers:
                canvas.create_line(width/2, height, center, bottom, fill=color, dash=(3, 4))
        if self.settings.show_fov:
            radius = fov_radius(width, self.settings.camera_fov, self.settings.selection_fov)
            canvas.create_oval(width/2-radius, height/2-radius, width/2+radius, height/2+radius, outline="#4d6b8d", dash=(4, 4))
        canvas.create_line(width/2-7, height/2, width/2+7, height/2, fill="#e1e9f4")
        canvas.create_line(width/2, height/2-7, width/2, height/2+7, fill="#e1e9f4")
        canvas.create_text(16, 18, anchor="nw", fill="#dce7f8", font=("Segoe UI", 11),
                           text="SIMULATED DATA ONLY\n%.0f FPS · %d/%d actors in view · t %.1fs%s\nTarget: %s" %
                           (self.fps, rendered, len(players), self.sim.time, " · PAUSED" if self.paused else "",
                            ("Player %02d" % self.target.id) if self.target else "none in selection FOV"))
        canvas.create_text(16, height-16, anchor="sw", fill="#889cb6", text="Camera %.1f, %.1f, %.1fm · yaw %.1f° · pitch %.1f°" %
                           (self.camera.position.x, self.camera.position.y, self.camera.position.z, self.camera.yaw, self.camera.pitch))

    def help(self):
        messagebox.showinfo("Simulation profile / controls",
            "Intended environment: " + self.profile["intended_environment"] +
            "\nLive integration: UNAVAILABLE / UNTESTED\nVerified offsets: none\n\n" +
            "This application visualizes deterministic synthetic players inside its own window. Visibility is synthetic.\n\n" +
            "Click scene, WASD move, Q/E vertical. Drag to look. Space pauses actor motion; camera remains interactive. R resets.\n" +
            "Follow changes only this simulation camera. Smoothness is a time constant; lower is faster. Selection FOV is a full cone angle.\n\n" +
            "Settings/logs: " + str(self.directory), parent=self.root)

    def close(self):
        for job in (self.save_job, self.frame_job):
            if job:
                self.root.after_cancel(job)
        self.save()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Standalone Simulation Lab")
    parser.add_argument("--settings-dir", type=Path)
    parser.add_argument("--smoke-test", type=Path, help="Write GUI smoke result then exit")
    args = parser.parse_args()
    if args.smoke_test and args.smoke_test.exists():
        args.smoke_test.unlink()
    directory = args.settings_dir or Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "SimulationLab"
    root = tk.Tk()
    app = App(root, directory)
    if args.smoke_test:
        def smoke_failure(kind, error, traceback):
            logging.error("Smoke callback failed", exc_info=(kind, error, traceback))
            root.destroy()
        root.report_callback_exception = smoke_failure
        def smoke():
            try:
                assert root.winfo_width() >= 1000
                assert len(app.canvas.find_all()) > 20
                assert len(app.variables) == len(fields(Settings))
                app.variables["player_count"].set(32)
                app.changed("player_count")
                assert len(app.sim.players) == 32
                app.toggle_pause()
                assert app.paused
                app.defaults()
                assert Settings.load(app.config_path) == Settings()
                assert app.profile["live_integration_tested"] is False
                args.smoke_test.write_text(json.dumps({"status": "passed", "version": VERSION, "canvas_items": len(app.canvas.find_all()),
                                                       "platform": sys.platform, "live_integration": False}, indent=2), encoding="utf-8")
            except Exception:
                logging.exception("GUI smoke failed")
                root.destroy()
                raise
            app.close()
        root.after(700, smoke)
    root.mainloop()
    if args.smoke_test:
        if not args.smoke_test.exists():
            raise SystemExit(1)
        if json.loads(args.smoke_test.read_text(encoding="utf-8")).get("status") != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
