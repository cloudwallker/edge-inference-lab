import copy
import unittest
from collections import Counter
from .fixtures import small_config


class TraceTests(unittest.TestCase):
    def setUp(self):
        from edge_inference_lab.config import Config
        from edge_inference_lab.traces import generate_traces, validate_pairing
        self.Config = Config
        self.generate = generate_traces
        self.validate = validate_pairing

    def test_pairing_preserves_fixed_fields_and_block_marginals(self):
        config = self.Config.from_dict(small_config())
        traces = self.generate(config, 17)
        self.assertEqual(set(traces), {"high_tight", "high_loose", "random", "switch"})
        base = traces["high_tight"]
        self.assertEqual(len(base), 64)
        for trace in traces.values():
            self.assertEqual([(r.id, r.slot, r.source, r.model, r.data_mb) for r in trace],
                             [(r.id, r.slot, r.source, r.model, r.data_mb) for r in base])
            for block in range(4):
                rows = [r for r in trace if r.slot // 2 == block]
                reference = [r for r in base if r.slot // 2 == block]
                self.assertEqual(Counter(r.min_accuracy for r in rows), Counter(r.min_accuracy for r in reference))
                self.assertEqual(Counter(r.deadline_ms for r in rows), Counter(r.deadline_ms for r in reference))
        self.validate(traces, 2)

    def test_opposite_pairs_and_switch_are_explicit(self):
        traces = self.generate(self.Config.from_dict(small_config()), 17)
        self.assertEqual({(r.min_accuracy, r.deadline_ms) for r in traces["high_tight"]},
                         {(0.5, 200), (0.8, 40)})
        self.assertEqual({(r.min_accuracy, r.deadline_ms) for r in traces["high_loose"]},
                         {(0.5, 40), (0.8, 200)})
        for index, r in enumerate(traces["switch"]):
            source = "high_tight" if r.slot < 4 else "high_loose"
            self.assertEqual(r, traces[source][index])

    def test_generator_is_reproducible_and_validator_catches_confounds(self):
        config = self.Config.from_dict(small_config())
        traces = self.generate(config, 23)
        self.assertEqual(traces, self.generate(config, 23))
        from dataclasses import replace
        altered = copy.deepcopy(traces)
        altered["random"][0] = replace(altered["random"][0], source="b" if altered["random"][0].source == "a" else "a")
        with self.assertRaisesRegex(ValueError, "fixed"):
            self.validate(altered, 2)

    def test_invalid_configuration_rejects_nan_and_impossible_floor(self):
        for value in [float("nan"), float("inf"), -1]:
            raw = small_config()
            raw["nodes"][0]["capacity"] = value
            with self.assertRaises(ValueError):
                self.Config.from_dict(raw)
        raw = small_config()
        raw["nodes"][0]["capacity"] = 1
        with self.assertRaisesRegex(ValueError, "floor"):
            self.Config.from_dict(raw)

    def test_invalid_link_and_seed_overlap_are_errors(self):
        raw = small_config()
        raw["links"][0]["target"] = "missing"
        with self.assertRaises(ValueError):
            self.Config.from_dict(raw)

    def test_unused_payment_keys_cannot_change_online_bounds(self):
        raw = small_config()
        raw["pricing"]["payments"]["unused"] = {"unused": [100]}
        with self.assertRaisesRegex(ValueError, "pricing"):
            self.Config.from_dict(raw)

    def test_malformed_model_container_and_zero_grid_resources_fail_cleanly(self):
        for value in [None, []]:
            raw = small_config()
            raw["models"] = value
            with self.assertRaises(ValueError):
                self.Config.from_dict(raw)
        raw = small_config()
        raw["models"]["toy"][0]["vcpu"] = 1e-10
        with self.assertRaisesRegex(ValueError, "resource_unit"):
            self.Config.from_dict(raw)
        raw = small_config()
        raw["algorithm"]["floor"] = 0
        raw["nodes"][0]["capacity"] = 5e-11
        with self.assertRaisesRegex(ValueError, "resource_unit"):
            self.Config.from_dict(raw)
        raw = small_config()
        raw["seeds"]["test"] = [1]
        with self.assertRaisesRegex(ValueError, "seed"):
            self.Config.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
