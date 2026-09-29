import unittest
from dataclasses import replace
from .fixtures import small_config
from edge_inference_lab.config import Config
from edge_inference_lab.domain import Request


class ModelTests(unittest.TestCase):
    def setUp(self):
        from edge_inference_lab.network import Network
        from edge_inference_lab.economics import evaluate, payment
        self.Network, self.evaluate, self.payment = Network, evaluate, payment
        self.config = Config.from_dict(small_config())

    def test_latency_cost_and_cold_delay_match_hand_calculation(self):
        req = Request("one", 0, "a", "toy", 0.5, 200, 1)
        route = self.Network(self.config).route("a", "b")
        resolution = self.config.models["toy"][0]
        warm = self.evaluate(self.config, req, "b", resolution, route, False)
        self.assertAlmostEqual(warm.delay_ms, 16)
        self.assertAlmostEqual(warm.payment, 0.06)
        self.assertAlmostEqual(warm.upload_cost, 0.000004)
        self.assertAlmostEqual(warm.link_cost, 0.01)
        self.assertAlmostEqual(warm.inference_cost, 0.02)
        self.assertAlmostEqual(warm.profit, 0.029996)
        cold = self.evaluate(self.config, req, "b", resolution, route, True)
        self.assertAlmostEqual(cold.delay_ms, 36)
        self.assertAlmostEqual(cold.profit, warm.profit)

    def test_inference_cost_and_time_are_per_request(self):
        req = Request("two", 0, "a", "toy", 0.5, 200, 2)
        value = self.evaluate(self.config, req, "b", self.config.models["toy"][0],
                              self.Network(self.config).route("a", "b"), False)
        self.assertAlmostEqual(value.delay_ms, 22)
        self.assertAlmostEqual(value.inference_cost, 0.02)
        self.assertAlmostEqual(value.upload_cost, 0.000008)
        self.assertAlmostEqual(value.link_cost, 0.02)

    def test_accuracy_and_deadline_are_checked_independently(self):
        req = Request("one", 0, "a", "toy", 0.8, 25, 1)
        route = self.Network(self.config).route("a", "a")
        low, high = self.config.models["toy"]
        self.assertFalse(self.evaluate(self.config, req, "a", low, route, False).accuracy_ok)
        self.assertTrue(self.evaluate(self.config, req, "a", high, route, False).deadline_ok)
        self.assertFalse(self.evaluate(self.config, req, "a", high, route, True).deadline_ok)
        self.assertAlmostEqual(self.payment(self.config, req), 0.12)

    def test_shortest_delay_path_is_not_cheapest_path(self):
        raw = small_config()
        raw["nodes"].append({"id": "c", "capacity": 4, "upload_mbps": 2000, "upload_cost_per_second": 0.001})
        raw["links"] = [
            {"source": "a", "target": "b", "latency_ms_per_mb": 1, "cost_per_mb": 0.01},
            {"source": "b", "target": "c", "latency_ms_per_mb": 1, "cost_per_mb": 0.02},
            {"source": "a", "target": "c", "latency_ms_per_mb": 3, "cost_per_mb": 0.005},
        ]
        route = self.Network(Config.from_dict(raw)).route("a", "c")
        self.assertEqual(route.nodes, ("a", "b", "c"))
        self.assertEqual(route.latency_ms_per_mb, 2)
        self.assertAlmostEqual(route.cost_per_mb, 0.03)


if __name__ == "__main__":
    unittest.main()
