import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import state_machine as sm


def run(s, et, **p):
    s, log, d = sm.handle(s, et, p)
    return s, log, d


class AwayMode(unittest.TestCase):
    def away(self):
        return run(sm.initial_state(), "ACTIVATE_AWAY")[0]

    def test_pump_anomaly_contained(self):
        s, log, d = run(self.away(), "SIMULATE_WATER_ANOMALY")
        self.assertEqual(d["action"], "STOP_PUMP")
        self.assertEqual(d["status"], "CONTAINED")
        self.assertEqual(s["pump_state"], "OFF")
        self.assertIn("TANK_NOT_RISING", d["evidence_codes"])

    def test_leak_uses_close_inlet(self):
        _, _, d = run(self.away(), "SIMULATE_WATER_ANOMALY", anomaly_type="LEAK_FLOW")
        self.assertEqual(d["action"], "CLOSE_INLET")

    def test_valve_failure_escalates(self):
        s = run(self.away(), "SET_VALVE_FAILURE", enabled=True)[0]
        s, log, d = run(s, "SIMULATE_WATER_ANOMALY")
        self.assertEqual(d["status"], "ESCALATED")
        self.assertEqual(s["water_flow_lpm"], 3.8)
        self.assertEqual(log[-1]["event_type"], "ESCALATION")

    def test_home_mode_not_escalated(self):
        s, _, d = run(sm.initial_state(), "SIMULATE_WATER_ANOMALY")
        self.assertEqual(d["status"], "NORMAL_USE")
        self.assertIsNone(s["active_incident"])

    def test_bad_inputs_rejected(self):
        with self.assertRaises(sm.Rejected):
            run(sm.initial_state(), "FORMAT_DISK")
        with self.assertRaises(sm.Rejected):
            run(sm.initial_state(), "SIMULATE_WATER_ANOMALY", anomaly_type="x")


class RainSafe(unittest.TestCase):
    def to_check(self):
        s = run(sm.initial_state(), "START_RAIN")[0]
        self.assertEqual((s["rain_safe_state"], s["gate_state"]), ("FIRST_FLUSH", "CLOSED"))
        return run(s, "FIRST_FLUSH_DONE")[0]

    def test_sample_before_first_flush_rejected(self):
        s = run(sm.initial_state(), "START_RAIN")[0]
        with self.assertRaises(sm.Rejected):
            run(s, "SUBMIT_SAMPLE", profile="GOOD")

    def test_poor_sample_keeps_gate_closed(self):
        s = run(self.to_check(), "SUBMIT_SAMPLE", profile="POOR")[0]
        self.assertEqual((s["rain_safe_state"], s["gate_state"]), ("REJECTED", "CLOSED"))

    def test_missing_sample_is_sensor_fault(self):
        s = run(self.to_check(), "SUBMIT_SAMPLE", profile="MISSING")[0]
        self.assertEqual((s["rain_safe_state"], s["gate_state"]), ("SENSOR_FAULT", "CLOSED"))

    def test_good_sample_fills_then_closes(self):
        s = run(self.to_check(), "SUBMIT_SAMPLE", profile="GOOD")[0]
        self.assertEqual(s["gate_state"], "OPEN")
        for _ in range(10):
            if s["rain_safe_state"] != "COLLECTING":
                break
            s = run(s, "FILL_TICK")[0]
        self.assertEqual((s["tank_level_percent"], s["rain_safe_state"], s["gate_state"]), (100, "TANK_FULL", "CLOSED"))

    def test_gate_fault_stops_collection(self):
        s = run(self.to_check(), "SUBMIT_SAMPLE", profile="GOOD")[0]
        s = run(s, "SIMULATE_GATE_FAULT")[0]
        self.assertEqual((s["rain_safe_state"], s["gate_state"]), ("ACTUATOR_FAULT", "FAULT"))


class Persistence(unittest.TestCase):
    def test_decision_saved_in_state_and_cleared_by_new_rain(self):
        s = run(sm.initial_state(), "ACTIVATE_AWAY")[0]
        s = run(s, "SIMULATE_WATER_ANOMALY")[0]
        self.assertEqual(s["last_decision"]["action"], "STOP_PUMP")
        self.assertEqual(run(s, "START_RAIN")[0]["last_decision"], None)

    def test_dynamodb_number_roundtrip(self):
        import storage
        s = run(run(sm.initial_state(), "ACTIVATE_AWAY")[0], "SIMULATE_WATER_ANOMALY")[0]
        self.assertEqual(storage._plain(storage._clean(s)), s)


class Handler(unittest.TestCase):
    def test_http_roundtrip(self):
        import json, handler
        ev = lambda m, p, b=None: {"requestContext": {"http": {"method": m}}, "rawPath": p, "body": b}
        r = handler.lambda_handler(ev("POST", "/event", json.dumps({"event_type": "ACTIVATE_AWAY"})))
        self.assertEqual(r["statusCode"], 200)
        r = handler.lambda_handler(ev("GET", "/snapshot"))
        self.assertEqual(json.loads(r["body"])["state"]["mode"], "AWAY")
        r = handler.lambda_handler(ev("POST", "/event", json.dumps({"event_type": "NOPE"})))
        self.assertEqual(r["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
