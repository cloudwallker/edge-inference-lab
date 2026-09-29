import math
import unittest
from dataclasses import replace
from .fixtures import small_config
from edge_inference_lab.config import Config
from edge_inference_lab.domain import Request


def one_node_config(single_resolution=False):
    raw = small_config()
    raw["nodes"] = raw["nodes"][:1]
    raw["links"] = []
    if single_resolution:
        raw["models"]["toy"] = raw["models"]["toy"][:1]
        raw["pricing"]["payments"]["toy"].pop("high")
    return Config.from_dict(raw)


def burst(slot, count=4, accuracy=0.5, deadline=200):
    return [Request(f"{slot}-{i}", slot, "a", "toy", accuracy, deadline, 1) for i in range(count)]


class DualTests(unittest.TestCase):
    def test_numerically_unusable_bounds_are_reported_as_configuration_errors(self):
        from edge_inference_lab.policies import Bounds
        raw = small_config()
        raw["nodes"] = raw["nodes"][:1]
        raw["links"] = []
        raw["nodes"][0]["capacity"] = 1e100
        raw["models"]["toy"] = raw["models"]["toy"][:1]
        raw["models"]["toy"][0]["vcpu"] = 1e100
        raw["pricing"]["payments"]["toy"].pop("high")
        with self.assertRaisesRegex(ValueError, "bounds"):
            Bounds.from_config(Config.from_dict(raw))

    def test_selected_branch_updates_only_its_dual(self):
        from edge_inference_lab.policies import Bounds, DualState, Candidate
        from edge_inference_lab.economics import ServiceValue
        cfg = one_node_config()
        bounds = Bounds(phi1=0.1, phi2=0.01, rmax=1, nmax=0.5, a=2, b=2)
        state = DualState(cfg, {"a": 2}, {("a", "toy", "low"): 1}, bounds)
        val = ServiceValue(0.06, 0, 0, 0.02, 0.04, 10, True, True)
        res = cfg.models["toy"][0]
        candidate = Candidate("new", "a", "toy", res, val)
        chosen = state.choose([candidate])
        self.assertAlmostEqual(chosen.score, 0.04)
        state.update(chosen)
        self.assertAlmostEqual(state.alpha["a"], 0.025)
        self.assertEqual(state.beta[("a", "toy", "low")], 0)
        warm = state.choose([Candidate("existing", "a", "toy", res, val)])
        state.update(warm)
        self.assertAlmostEqual(state.beta[("a", "toy", "low")], 0.02)
        self.assertAlmostEqual(state.alpha["a"], 0.025)
        state.update(warm)
        self.assertAlmostEqual(state.beta[("a", "toy", "low")], 0.05)
        self.assertIsNone(state.choose([Candidate("existing", "a", "toy", res, val)]))


class SimulationTests(unittest.TestCase):
    def setUp(self):
        from edge_inference_lab.simulation import simulate
        from edge_inference_lab.policies import Policy
        self.simulate, self.Policy = simulate, Policy
        self.config = one_node_config()

    def requests(self, run):
        return [e for e in run.events if e["kind"] == "request"]

    def test_cold_requests_group_into_one_instance_and_warm_floor_is_preserved(self):
        run = self.simulate(one_node_config(True), burst(0), self.Policy("test", theta=2))
        reqs = self.requests(run)
        # Eq. (39): after one warm admission beta>0, the unpenalized new branch wins.
        # With C^t=3.5, phi1=.16 and a=2, the next new score .02856742857...
        # exceeds the warm .0239976; after two new updates warm wins again.
        self.assertEqual([r["mode"] for r in reqs], ["existing", "new", "new", "existing"])
        self.assertAlmostEqual(reqs[2]["score"], 0.02856742857142858)
        self.assertEqual(len({r["instance_id"] for r in reqs if r["mode"] == "new"}), 1)
        self.assertEqual(len([e for e in run.events if e["kind"] == "create" and not e["protected"]]), 1)
        releases = [e for e in run.events if e["kind"] == "release"]
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["slot"], 2)
        self.assertFalse(releases[0]["protected"])
        self.assertAlmostEqual(reqs[0]["delay_ms"], 14)
        self.assertAlmostEqual(reqs[1]["delay_ms"], 34)

    def test_extra_instance_retention_changes_reuse(self):
        requests = burst(0) + burst(3, deadline=20)
        cfg = one_node_config(True)
        short = self.simulate(cfg, requests, self.Policy("short", theta=2))
        long = self.simulate(cfg, requests, self.Policy("long", theta=4))
        self.assertEqual(sum(e["accepted"] for e in self.requests(short) if e["slot"] == 3), 2)
        self.assertEqual(sum(e["accepted"] for e in self.requests(long) if e["slot"] == 3), 4)
        self.assertEqual(sum(e["kind"] == "create" and not e["protected"] for e in long.events), 1)
        self.assertEqual([e["mode"] for e in self.requests(long) if e["slot"] == 3], ["existing"] * 4)

    def test_accuracy_and_deadline_rejections_are_not_cold_starts(self):
        requests = [Request("accuracy", 0, "a", "toy", 0.9, 200, 1),
                    Request("deadline", 0, "a", "toy", 0.5, 1, 1)]
        reqs = self.requests(self.simulate(self.config, requests, self.Policy("test")))
        self.assertEqual([r["reason"] for r in reqs], ["accuracy", "deadline"])
        self.assertTrue(all(r["instance_id"] is None and not r["accepted"] for r in reqs))

    def test_hard_cap_greedy_enforces_l_and_capacity(self):
        raw = small_config()
        raw["nodes"] = raw["nodes"][:1]
        raw["nodes"][0]["capacity"] = 1.5
        raw["links"] = []
        cfg = Config.from_dict(raw)
        reqs = self.requests(self.simulate(cfg, burst(0, 12), self.Policy("greedy", admission="greedy")))
        self.assertEqual(sum(r["accepted"] for r in reqs), 4)
        self.assertTrue(all(r["reason"] == "strict_resource" for r in reqs if not r["accepted"]))

    def test_dual_slack_is_recorded_instead_of_hidden_capacity_truncation(self):
        policy = self.Policy("uncontrolled", no_control=True)
        run = self.simulate(self.config, burst(0, 30), policy)
        slots = [e for e in run.events if e["kind"] == "slot_end"]
        self.assertTrue(any(e["resource_violation_vcpu"] > 0 or e["warm_slot_violation"] > 0 for e in slots))
        self.assertEqual(sum(e["accepted"] for e in self.requests(run)), 30)

    def test_no_pre_new_only_has_no_floor_or_zero_division(self):
        run = self.simulate(self.config, burst(0) + burst(3), self.Policy("new_only", preload=False))
        self.assertTrue(all(e["mode"] == "new" for e in self.requests(run) if e["accepted"]))
        self.assertTrue(all(not e["protected"] for e in run.events if e["kind"] == "create"))
        self.assertTrue(all(math.isfinite(e["profit"]) for e in self.requests(run)))

    def test_duplicate_bad_order_and_nonfinite_requests_fail(self):
        for rows in [burst(0) + [burst(0)[0]], burst(3) + burst(0),
                     [replace(burst(0)[0], data_mb=float("nan"))]]:
            with self.assertRaises(ValueError):
                self.simulate(self.config, rows, self.Policy("test"))

    def test_first_decision_does_not_depend_on_later_requests(self):
        first = burst(0, 1)
        a = self.requests(self.simulate(self.config, first, self.Policy("test")))[0]
        b = self.requests(self.simulate(self.config, first + burst(1, 30), self.Policy("test")))[0]
        self.assertEqual(a, b)

    def test_near_grid_capacity_does_not_create_false_positive_residual(self):
        raw = small_config()
        raw["nodes"] = raw["nodes"][:1]
        raw["nodes"][0]["capacity"] = 0.5000000001
        raw["links"] = []
        raw["models"]["toy"] = raw["models"]["toy"][:1]
        raw["pricing"]["payments"]["toy"].pop("high")
        run = self.simulate(Config.from_dict(raw), burst(0), self.Policy("test"))
        self.assertEqual(sum(e["kind"] == "create" and not e["protected"] for e in run.events), 0)
        self.assertEqual(sum(r["accepted"] for r in self.requests(run)), 2)


if __name__ == "__main__":
    unittest.main()
