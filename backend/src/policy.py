"""Deterministic policy rules. Demo thresholds only - NOT calibrated safety or drinking-water standards.
All values are overridable with environment variables."""
import os

def _f(name, default):
    return float(os.getenv(name, default))

CFG = {
    "FLOW_THRESHOLD": _f("FLOW_THRESHOLD", 1.0),          # L/min
    "DURATION_THRESHOLD": _f("DURATION_THRESHOLD", 120),  # seconds
    "TANK_RISE_MIN": _f("TANK_RISE_MIN", 0.5),            # % rise expected while pump runs
    "VERIFY_MAX_FLOW": _f("VERIFY_MAX_FLOW", 0.5),        # L/min after action = contained
    "PH_MIN": _f("PH_MIN", 6.0), "PH_MAX": _f("PH_MAX", 8.5),
    "TURBIDITY_MAX_NTU": _f("TURBIDITY_MAX_NTU", 5.0),
    "TDS_MAX_PPM": _f("TDS_MAX_PPM", 300.0),
}

# Server-side sample presets: the browser may only pick a profile name, never raw readings.
SAMPLES = {
    "GOOD": {"ph": 6.9, "turbidity_ntu": 2.1, "tds_ppm": 48.0},
    "POOR": {"ph": 4.1, "turbidity_ntu": 19.0, "tds_ppm": 520.0},
    "MISSING": {"ph": None, "turbidity_ntu": None, "tds_ppm": None},
}


def _decision(incident, severity, evidence, action, status, explanation):
    return {
        "incident": incident, "severity": severity, "evidence_codes": evidence,
        "action": action, "verification_required": action in ("STOP_PUMP", "CLOSE_INLET"),
        "status": status, "explanation": explanation,
    }


def evaluate_anomaly(sim):
    """Away Mode water anomaly policy. Action always comes from this allowlist."""
    needed = ("mode", "occupancy", "water_flow_lpm", "flow_duration_seconds")
    if any(sim.get(k) is None for k in needed):
        return _decision("UNCERTAIN_READINGS", "MEDIUM", ["MISSING_READING"], "MONITOR_AND_NOTIFY",
                         "SUSPICIOUS", "Readings are incomplete, so no shutoff was attempted. "
                         "Owner notification recommended; cause not confirmed.")
    if not (sim["mode"] == "AWAY" and sim["occupancy"] == 0):
        return _decision(None, "LOW", ["HOME_OCCUPIED"], "NONE", "NORMAL_USE",
                         "Flow matches expected household use while someone is home. No action taken.")
    ev = ["AWAY_MODE", "NO_OCCUPANCY"]
    if sim["water_flow_lpm"] > CFG["FLOW_THRESHOLD"] and sim["flow_duration_seconds"] >= CFG["DURATION_THRESHOLD"]:
        ev.append("SUSTAINED_FLOW")
        rise = sim["tank_after"] - sim["tank_before"]
        if sim["pump_state"] == "ON" and rise < CFG["TANK_RISE_MIN"]:
            ev += ["PUMP_ON", "TANK_NOT_RISING"]
            return _decision("PROBABLE_WATER_SYSTEM_ANOMALY", "HIGH", ev, "STOP_PUMP", "VERIFYING",
                             "Sustained flow occurred while the home was away, and the tank level did not rise "
                             "while the pump was running. This suggests a water-system anomaly; the exact "
                             "physical cause is not confirmed.")
        if rise < 0:
            ev.append("TANK_FALLING")
        return _decision("PROBABLE_WATER_SYSTEM_ANOMALY", "HIGH", ev, "CLOSE_INLET", "VERIFYING",
                         "Sustained flow occurred while the home was away with no pump explanation. This "
                         "suggests a water-system anomaly; cause and location are not confirmed.")
    return _decision("SUSPICIOUS_FLOW", "MEDIUM", ev, "MONITOR_AND_NOTIFY", "SUSPICIOUS",
                     "Flow pattern is unusual but evidence is incomplete. Monitoring; no shutoff attempted.")


def evaluate_sample(sample):
    """Returns (PASSED | FAILED | SENSOR_FAULT, reason codes)."""
    ph, ntu, tds = (sample.get(k) for k in ("ph", "turbidity_ntu", "tds_ppm"))
    if None in (ph, ntu, tds):
        return "SENSOR_FAULT", ["MISSING_READING"]
    fails = []
    if not CFG["PH_MIN"] <= ph <= CFG["PH_MAX"]:
        fails.append("PH_OUT_OF_RANGE")
    if ntu > CFG["TURBIDITY_MAX_NTU"]:
        fails.append("TURBIDITY_HIGH")
    if tds > CFG["TDS_MAX_PPM"]:
        fails.append("TDS_HIGH")
    return ("FAILED" if fails else "PASSED"), fails


def gate_preconditions(state, sample_result):
    checks = {
        "first_flush_complete": bool(state["first_flush_complete"]),
        "sample_valid": sample_result != "SENSOR_FAULT",
        "readings_in_range": sample_result == "PASSED",
        "tank_below_full": state["tank_level_percent"] < 100,
        "no_fault_active": state["gate_state"] != "FAULT",
    }
    return all(checks.values()), checks
