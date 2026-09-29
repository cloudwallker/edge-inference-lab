def small_config():
    return {
        "nodes": [
            {"id": "a", "capacity": 4, "upload_mbps": 2000, "upload_cost_per_second": 0.001},
            {"id": "b", "capacity": 4, "upload_mbps": 2000, "upload_cost_per_second": 0.001},
        ],
        "links": [{"source": "a", "target": "b", "latency_ms_per_mb": 2, "cost_per_mb": 0.01}],
        "models": {"toy": [
            {"id": "low", "accuracy": 0.5, "vcpu": 0.5, "inference_ms": 10,
             "init_ms": 20, "cost": 0.02},
            {"id": "high", "accuracy": 0.8, "vcpu": 1, "inference_ms": 20,
             "init_ms": 30, "cost": 0.04},
        ]},
        "workload": {"slots": 8, "requests_per_slot": 8, "block_slots": 2, "switch_slot": 4,
                     "data_mb": [0.5, 2], "deadline_ms": [40, 200]},
        "algorithm": {"concurrency": 2, "floor": 1, "theta": 2, "resource_unit": 0.5},
        "pricing": {"deadline_levels_ms": [50, 200],
                    "payments": {"toy": {"low": [0.08, 0.06], "high": [0.12, 0.1]}}},
        "seeds": {"development": [1, 2], "test": list(range(101, 111))},
    }
