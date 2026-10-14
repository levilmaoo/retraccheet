"""Standalone simulation mathematics. No process access or game integration."""
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path
import random


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def __sub__(self, other):
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def length(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


@dataclass
class Camera:
    position: Vec3
    yaw: float = 0.0
    pitch: float = 0.0


@dataclass
class Settings:
    camera_fov: float = 90.0
    selection_fov: float = 30.0
    smoothness: float = 0.35
    max_distance: float = 100.0
    player_count: int = 16
    speed: float = 1.0
    boxes: bool = True
    skeletons: bool = True
    labels: bool = True
    health_bars: bool = True
    tracers: bool = False
    show_fov: bool = True
    include_teammates: bool = False
    visible_only: bool = True
    follow: bool = False
    selection: str = "Crosshair"
    aim_point: str = "Head"

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported settings schema (expected 1)")
        values = data.get("settings")
        if not isinstance(values, dict):
            raise ValueError("Missing settings object")
        result = cls()
        ranges = {"camera_fov": (40, 120), "selection_fov": (2, 80),
                  "smoothness": (0.02, 2), "max_distance": (10, 200),
                  "player_count": (1, 64), "speed": (0, 3)}
        for field in fields(cls):
            if field.name not in values:
                continue
            value = values[field.name]
            default = getattr(result, field.name)
            if isinstance(default, bool):
                if type(value) is not bool:
                    raise ValueError(field.name + " must be boolean")
            elif field.name in ranges:
                low, high = ranges[field.name]
                if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
                    raise ValueError(field.name + " out of range")
                if field.name == "player_count" and int(value) != value:
                    raise ValueError("player_count must be an integer")
                value = int(value) if field.name == "player_count" else float(value)
            elif value not in ({"selection": ("Crosshair", "Distance", "Health"),
                                "aim_point": ("Head", "Chest")}[field.name]):
                raise ValueError("Invalid " + field.name)
            setattr(result, field.name, value)
        return result

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"schema_version": 1, "settings": asdict(self)}, indent=2), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def camera_space(point, camera):
    """Right-handed world: +X forward, +Y right, +Z up; angles in degrees."""
    delta = point - camera.position
    yaw, pitch = math.radians(camera.yaw), math.radians(camera.pitch)
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    return (delta.x * cy * cp + delta.y * sy * cp + delta.z * sp,
            -delta.x * sy + delta.y * cy,
            -delta.x * cy * sp - delta.y * sy * sp + delta.z * cp)


def project(point, camera, width, height, horizontal_fov):
    if width <= 0 or height <= 0 or not 0 < horizontal_fov < 180:
        return None
    depth, right, up = camera_space(point, camera)
    if depth <= 0.05:
        return None
    focal = width / (2 * math.tan(math.radians(horizontal_fov / 2)))
    return width / 2 + focal * right / depth, height / 2 - focal * up / depth


def fov_radius(width, camera_fov, selection_fov):
    return width / 2 * math.tan(math.radians(selection_fov / 2)) / math.tan(math.radians(camera_fov / 2))


@dataclass
class Player:
    id: int
    origin: Vec3
    phase: float
    health: float
    teammate: bool
    visible: bool = True

    def position(self, time):
        return Vec3(self.origin.x + math.sin(time * 0.55 + self.phase) * 3,
                    self.origin.y + math.cos(time * 0.4 + self.phase) * 3, 0)

    def point(self, time, kind="Head"):
        p = self.position(time)
        return Vec3(p.x, p.y, 1.72 if kind == "Head" else 1.15)


class Simulation:
    def __init__(self, count=16, seed=1460):
        self.time = 0.0
        rng = random.Random(seed)
        self.players = [Player(i + 1, Vec3(rng.uniform(12, 80), rng.uniform(-35, 35), 0),
                               rng.uniform(0, 6.28), rng.randint(20, 100), i % 4 == 0)
                        for i in range(count)]
        self.update(0)

    def update(self, dt):
        self.time += dt
        for player in self.players:
            # Deterministic synthetic visibility; no live line-of-sight claims.
            player.visible = math.sin(self.time * 0.3 + player.phase) > -0.5


def select_target(players, time, camera, width, height, settings):
    candidates = []
    for player in players:
        if player.health <= 0 or (player.teammate and not settings.include_teammates):
            continue
        if settings.visible_only and not player.visible:
            continue
        point = player.point(time, settings.aim_point)
        distance = (point - camera.position).length()
        pixel = project(point, camera, width, height, settings.camera_fov)
        if distance > settings.max_distance or pixel is None:
            continue
        if not (0 <= pixel[0] <= width and 0 <= pixel[1] <= height):
            continue
        depth, right, up = camera_space(point, camera)
        angle = math.degrees(math.atan2(math.hypot(right, up), depth))
        if angle > settings.selection_fov / 2:
            continue
        metric = {"Crosshair": angle, "Distance": distance, "Health": player.health}[settings.selection]
        candidates.append((metric, player.id, player))
    return min(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def follow_target(camera, point, dt, smoothness):
    delta = point - camera.position
    yaw = math.degrees(math.atan2(delta.y, delta.x))
    pitch = math.degrees(math.atan2(delta.z, math.hypot(delta.x, delta.y)))
    alpha = 1 - math.exp(-max(0, dt) / max(0.001, smoothness))
    camera.yaw = (camera.yaw + ((yaw - camera.yaw + 180) % 360 - 180) * alpha + 180) % 360 - 180
    camera.pitch = max(-85, min(85, camera.pitch + (pitch - camera.pitch) * alpha))
