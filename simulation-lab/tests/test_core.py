import json
import math
from pathlib import Path
import tempfile
import unittest

from core import Camera, Player, Settings, Simulation, Vec3, camera_space, follow_target, fov_radius, project, select_target


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.camera = Camera(Vec3(0, 0, 0))

    def test_center_and_horizontal_fov(self):
        self.assertEqual(project(Vec3(10, 0, 0), self.camera, 1000, 600, 90), (500, 300))
        x, y = project(Vec3(10, 10, 0), self.camera, 1000, 600, 90)
        self.assertAlmostEqual(x, 1000)
        self.assertAlmostEqual(y, 300)

    def test_aspect_ratio_preserves_pixel_scale(self):
        self.assertEqual(project(Vec3(10, 0, 1), self.camera, 1000, 600, 90), (500, 250))
        self.assertEqual(project(Vec3(10, 0, 1), self.camera, 1000, 1000, 90), (500, 450))

    def test_behind_and_near_plane(self):
        for x in (-10, 0, .04):
            self.assertIsNone(project(Vec3(x, 0, 0), self.camera, 1000, 600, 90))

    def test_invalid_viewport_and_fov(self):
        self.assertIsNone(project(Vec3(10, 0, 0), self.camera, 0, 600, 90))
        self.assertIsNone(project(Vec3(10, 0, 0), self.camera, 1000, 600, 180))

    def test_rotated_and_translated_camera(self):
        camera = Camera(Vec3(2, 3, 4), 90, 0)
        point = project(Vec3(2, 13, 4), camera, 1000, 600, 90)
        self.assertAlmostEqual(point[0], 500)
        self.assertAlmostEqual(point[1], 300)
        camera = Camera(Vec3(0, 0, 0), 0, 45)
        self.assertAlmostEqual(camera_space(Vec3(10, 0, 10), camera)[2], 0)

    def test_fov_circle_matches_cone_projection(self):
        width, camera_fov, selection_fov = 1000, 90, 30
        pixel = project(Vec3(10, 10 * math.tan(math.radians(15)), 0), self.camera, width, 600, camera_fov)
        self.assertAlmostEqual(pixel[0] - width / 2, fov_radius(width, camera_fov, selection_fov))


class StaticPlayer(Player):
    def position(self, time):
        return self.origin


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.camera = Camera(Vec3(0, 0, 1.72))
        self.settings = Settings()
        self.a = StaticPlayer(1, Vec3(20, 1, 0), 0, 80, False)
        self.b = StaticPlayer(2, Vec3(10, 2, 0), 0, 30, False)

    def select(self, players):
        return select_target(players, 0, self.camera, 1000, 600, self.settings)

    def test_selection_modes(self):
        self.assertEqual(self.select([self.a, self.b]).id, 1)
        self.settings.selection = "Distance"
        self.assertEqual(self.select([self.a, self.b]).id, 2)
        self.settings.selection = "Health"
        self.assertEqual(self.select([self.a, self.b]).id, 2)

    def test_teammate_and_visibility_filters(self):
        self.a.teammate = True
        self.b.visible = False
        self.assertIsNone(self.select([self.a, self.b]))
        self.settings.include_teammates = True
        self.assertEqual(self.select([self.a, self.b]).id, 1)
        self.settings.include_teammates = False
        self.settings.visible_only = False
        self.assertEqual(self.select([self.a, self.b]).id, 2)

    def test_dead_far_behind_and_outside_fov(self):
        self.a.health = 0
        self.b.origin.x = 201
        self.assertIsNone(self.select([self.a, self.b]))
        self.b.origin = Vec3(-10, 0, 0)
        self.assertIsNone(self.select([self.b]))
        self.b.origin = Vec3(10, 10, 0)
        self.assertIsNone(self.select([self.b]))

    def test_offscreen_excluded_even_with_wide_selection(self):
        self.settings.camera_fov = 40
        self.settings.selection_fov = 80
        self.b.origin = Vec3(10, 5, 0)
        self.assertIsNone(self.select([self.b]))

    def test_stable_ties_and_empty(self):
        self.b.origin = self.a.origin
        self.assertEqual(self.select([self.b, self.a]).id, 1)
        self.assertIsNone(self.select([]))


class SmoothingTests(unittest.TestCase):
    def test_frame_rate_independence(self):
        cameras = []
        for fps in (30, 60, 144):
            camera = Camera(Vec3(0, 0, 0))
            for frame in range(fps):
                follow_target(camera, Vec3(10, 10, 3), 1/fps, .35)
            cameras.append(camera)
        for camera in cameras[1:]:
            self.assertAlmostEqual(camera.yaw, cameras[0].yaw)
            self.assertAlmostEqual(camera.pitch, cameras[0].pitch)

    def test_shortest_wrap_and_no_overshoot(self):
        camera = Camera(Vec3(0, 0, 0), 179)
        point = Vec3(math.cos(math.radians(-179)), math.sin(math.radians(-179)), 0)
        follow_target(camera, point, .01, 1)
        self.assertTrue(179 < camera.yaw < 180)
        follow_target(camera, point, 100, .02)
        self.assertAlmostEqual(camera.yaw, -179)

    def test_zero_time_and_pitch_limit(self):
        camera = Camera(Vec3(0, 0, 0))
        follow_target(camera, Vec3(10, 10, 3), 0, .1)
        self.assertEqual(camera.yaw, 0)
        follow_target(camera, Vec3(0, 0, 100), 10, .1)
        self.assertEqual(camera.pitch, 85)


class PersistenceTests(unittest.TestCase):
    def test_roundtrip_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "settings.json"
            settings = Settings(follow=True, smoothness=.8, player_count=64)
            settings.save(path)
            self.assertEqual(settings, Settings.load(path))
            settings.boxes = False
            settings.save(path)
            self.assertEqual(settings, Settings.load(path))
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_invalid_values(self):
        for key, value in [("smoothness", float("nan")), ("camera_fov", 180), ("player_count", 4.5),
                           ("speed", True), ("boxes", 1), ("selection", "unknown"), ("aim_point", None)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                Settings.from_dict({"schema_version": 1, "settings": {key: value}})

    def test_missing_fields_use_defaults_and_unknown_ignored(self):
        self.assertEqual(Settings(), Settings.from_dict({"schema_version": 1, "settings": {"future": "ignored"}}))

    def test_invalid_schema_and_malformed_json(self):
        for data in ([], {"schema_version": 2}, {"schema_version": 1, "settings": []}):
            with self.assertRaises(ValueError):
                Settings.from_dict(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                Settings.load(path)


class SimulationTests(unittest.TestCase):
    def test_deterministic_reset_and_motion(self):
        a, b = Simulation(64), Simulation(64)
        self.assertEqual(a.players, b.players)
        original = a.players[0].position(0)
        a.update(.5)
        b.update(.5)
        self.assertEqual(a.players, b.players)
        self.assertEqual(a.time, b.time)
        self.assertNotEqual(original, a.players[0].position(a.time))

    def test_profile_truthfulness(self):
        path = Path(__file__).resolve().parents[1] / "profiles" / "fortnite-14.60.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(profile["verified_offsets"], {})
        self.assertFalse(profile["live_integration_tested"])
        self.assertEqual(profile["integration_status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
