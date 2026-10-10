"""Pure state machine: (state, event, params) -> (new_state, log events, decision). No AWS here."""
import copy
import uuid
from datetime import datetime, timezone

import policy

ALLOWED_EVENTS = {"ACTIVATE_AWAY", "ACTIVATE_HOME", "SIMULATE_WATER_ANOMALY", "SET_VALVE_FAILURE",
                  "START_RAIN", "FIRST_FLUSH_DONE", "SUBMIT_SAMPLE", "FILL_TICK",
                  "SIMULATE_GATE_FAULT", "RESET"}
ANOMALIES = {"PUMP_NO_RISE", "LEAK_FLOW"}
FILL_STEP = 8
RAIN_BUSY = {"RAIN_DETECTED", "FIRST_FLUSH", "QUALITY_CHECK", "COLLECTING"}


class Rejected(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def initial_state():
    return {
        "mode": "HOME", "occupancy": 3, "water_flow_lpm": 0.0, "pump_state": "OFF",
        "inlet_state": "OPEN", "tank_level_percent": 72, "rain_state": "NONE",
        "rain_safe_state": "IDLE", "gate_state": "CLOSED", "first_flush_complete": False,
        "last_sample": None, "last_decision": None, "active_incident": None, "valve_failure": False,
        "updated_at": now_iso(),
    }


def _ev(event_type, scenario, message, severity="INFO", evidence=None, decision="", action="", verification=""):
    return {"event_id": uuid.uuid4().hex[:12], "event_type": event_type, "scenario": scenario,
            "evidence_codes": evidence or [], "severity": severity, "decision": decision,
            "action_status": action, "verification_status": verification, "message": message,
            "created_at": now_iso()}


def _require(cond, code, msg):
    if not cond:
        raise Rejected(code, msg)


def handle(state, event_type, params=None):
    params = params or {}
    _require(event_type in ALLOWED_EVENTS, "UNKNOWN_EVENT", f"Unsupported event_type: {event_type}")
    s, log, decision = copy.deepcopy(state), [], None

    if event_type == "RESET":
        s = initial_state()
        log.append(_ev("RESET", "SYSTEM", "Scenario reset to the initial simulated home state."))

    elif event_type in ("ACTIVATE_AWAY", "ACTIVATE_HOME"):
        away = event_type == "ACTIVATE_AWAY"
        s["mode"], s["occupancy"] = ("AWAY", 0) if away else ("HOME", 3)
        log.append(_ev(event_type, "AWAY_MODE", "Away Mode on: occupancy 0." if away
                       else "Home Mode on: normal household use expected.", evidence=["AWAY_MODE"] if away else []))

    elif event_type == "SET_VALVE_FAILURE":
        enabled = params.get("enabled")
        _require(isinstance(enabled, bool), "BAD_PARAM", "enabled must be true or false")
        s["valve_failure"] = enabled
        log.append(_ev(event_type, "FAULT_INJECTION", "Simulated valve/pump actuator failure "
                       + ("armed: the next shutoff command will not take effect." if enabled else "cleared.")))

    elif event_type == "SIMULATE_WATER_ANOMALY":
        kind = params.get("anomaly_type", "PUMP_NO_RISE")
        _require(kind in ANOMALIES, "BAD_PARAM", f"anomaly_type must be one of {sorted(ANOMALIES)}")
        tank = s["tank_level_percent"]
        sim = {"mode": s["mode"], "occupancy": s["occupancy"], "water_flow_lpm": 3.8,
               "pump_state": "ON" if kind == "PUMP_NO_RISE" else "OFF", "tank_before": tank,
               "tank_after": tank if kind == "PUMP_NO_RISE" else tank - 1, "flow_duration_seconds": 240}
        s.update(water_flow_lpm=3.8, pump_state=sim["pump_state"], inlet_state="OPEN")
        decision = policy.evaluate_anomaly(sim)
        log.append(_ev(event_type, "WATER_ANOMALY", decision["explanation"], decision["severity"],
                       decision["evidence_codes"], decision["action"], "", decision["status"]))
        action = decision["action"]
        if action in ("STOP_PUMP", "CLOSE_INLET"):
            failed = s["valve_failure"]
            if not failed:
                if action == "STOP_PUMP":
                    s["pump_state"] = "OFF"
                else:
                    s["inlet_state"] = "CLOSED"
            before = 3.8
            after = before if failed else 0.1
            s["water_flow_lpm"] = after
            log.append(_ev("ACTION_EXECUTED", "WATER_ANOMALY",
                           f"Simulated {action} command issued by the policy engine.", action=f"{action}: COMMAND_ISSUED"))
            ok = after <= policy.CFG["VERIFY_MAX_FLOW"]
            status = "CONTAINED" if ok else "ESCALATED"
            decision.update(status=status, verification={"before": before, "after": after,
                                                          "result": "VERIFIED" if ok else "ACTION_FAILED"})
            log.append(_ev("VERIFICATION", "WATER_ANOMALY", f"Follow-up sample: flow {before} -> {after} L/min.",
                           "INFO" if ok else "HIGH", action=action, verification=status))
            if not ok:
                log.append(_ev("ESCALATION", "WATER_ANOMALY", "Action did not reduce flow. Owner notification "
                               "recommended: check the supply manually.", "CRITICAL", action=action, verification="ESCALATED"))
            s["active_incident"] = {"incident": decision["incident"], "status": status}
        elif decision["status"] == "NORMAL_USE":
            s.update(water_flow_lpm=0.0, pump_state="OFF", active_incident=None)
        else:
            s["active_incident"] = {"incident": decision["incident"], "status": decision["status"]}

    elif event_type == "START_RAIN":
        _require(s["rain_safe_state"] not in RAIN_BUSY, "SCENARIO_RUNNING", "RainSafe is already running.")
        s.update(rain_state="RAINING", rain_safe_state="FIRST_FLUSH", gate_state="CLOSED",
                 first_flush_complete=False, last_sample=None, last_decision=None)
        log.append(_ev("RAIN_DETECTED", "RAINSAFE", "Rain detected (simulated). Gate stays closed."))
        log.append(_ev("FIRST_FLUSH_STARTED", "RAINSAFE", "First-flush diversion running: initial roof runoff "
                       "is diverted away from the tank."))

    elif event_type == "FIRST_FLUSH_DONE":
        _require(s["rain_safe_state"] == "FIRST_FLUSH", "BAD_STATE", "No first flush in progress.")
        s.update(first_flush_complete=True, rain_safe_state="QUALITY_CHECK")
        log.append(_ev(event_type, "RAINSAFE", "First flush complete. Evaluating a sample under the configured policy."))

    elif event_type == "SUBMIT_SAMPLE":
        profile = params.get("profile")
        _require(profile in policy.SAMPLES, "BAD_PARAM", f"profile must be one of {sorted(policy.SAMPLES)}")
        _require(s["rain_safe_state"] == "QUALITY_CHECK", "BAD_STATE", "Not ready for a sample.")
        sample = dict(policy.SAMPLES[profile])
        result, reasons = policy.evaluate_sample(sample)
        ok, checks = policy.gate_preconditions(s, result)
        sample.update(result=result, reasons=reasons)
        s["last_sample"] = sample
        if ok:
            s.update(gate_state="OPEN", rain_safe_state="COLLECTING")
            log.append(_ev("SAMPLE_EVALUATED", "RAINSAFE", "Passed configured collection policy (demo thresholds). "
                           "Simulated gate opened.", evidence=["FIRST_FLUSH_DONE", "SAMPLE_PASSED", "TANK_HAS_CAPACITY"],
                           decision="OPEN_GATE", action="GATE: OPEN"))
        elif result == "SENSOR_FAULT":
            s.update(gate_state="CLOSED", rain_safe_state="SENSOR_FAULT")
            log.append(_ev("SAMPLE_EVALUATED", "RAINSAFE", "Required readings missing. Gate stays closed.", "HIGH",
                           reasons, "KEEP_CLOSED", "GATE: CLOSED"))
        elif not checks["tank_below_full"]:
            s.update(gate_state="CLOSED", rain_safe_state="TANK_FULL")
            log.append(_ev("SAMPLE_EVALUATED", "RAINSAFE", "Tank already full. Gate stays closed.", evidence=["TANK_FULL"],
                           decision="KEEP_CLOSED", action="GATE: CLOSED"))
        else:
            s.update(gate_state="CLOSED", rain_safe_state="REJECTED")
            log.append(_ev("SAMPLE_EVALUATED", "RAINSAFE", "Failed configured collection policy. Gate stays closed.",
                           "MEDIUM", reasons, "KEEP_CLOSED", "GATE: CLOSED"))

    elif event_type == "FILL_TICK":
        _require(s["rain_safe_state"] == "COLLECTING", "BAD_STATE", "Not collecting.")
        s["tank_level_percent"] = min(100, s["tank_level_percent"] + FILL_STEP)
        if s["tank_level_percent"] >= 100:
            s.update(gate_state="CLOSED", rain_safe_state="TANK_FULL", rain_state="NONE")
            log.append(_ev("TANK_FULL", "RAINSAFE", "Tank reached 100%. Simulated gate closed automatically.",
                           evidence=["TANK_FULL"], decision="CLOSE_GATE", action="GATE: CLOSED"))
        else:
            log.append(_ev(event_type, "RAINSAFE", f"Collecting: tank at {s['tank_level_percent']}%."))

    elif event_type == "SIMULATE_GATE_FAULT":
        _require(s["rain_safe_state"] == "COLLECTING", "BAD_STATE", "Gate fault can be injected while collecting.")
        s.update(gate_state="FAULT", rain_safe_state="ACTUATOR_FAULT")
        log.append(_ev(event_type, "RAINSAFE", "Gate actuator fault. Collection stopped; owner notification recommended.",
                       "HIGH", ["ACTUATOR_FAULT"], "STOP_COLLECTION", "GATE: FAULT"))

    if decision is not None:
        s["last_decision"] = decision  # persisted so the control center survives a page reload
    s["updated_at"] = now_iso()
    return s, log, decision
