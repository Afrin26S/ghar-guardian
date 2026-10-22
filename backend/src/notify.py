"""Owner alerts via Amazon SNS (email). Optional: active only when ALERT_TOPIC_ARN is set.
A failure to send is logged as a timeline event and never breaks the request.
Rate limited (ALERT_MIN_INTERVAL_SECONDS, default 300) so a public demo cannot flood the owner's inbox."""
import os
from datetime import datetime, timezone

import state_machine as sm

ALERT_EVENTS = {"ESCALATION", "SIMULATE_GATE_FAULT"}  # failed action / gate actuator fault
_client = None


def _sns():
    global _client
    if _client is None:
        import boto3
        _client = boto3.client("sns")
    return _client


def _compose(e):
    if e["event_type"] == "ESCALATION":
        subject = "Ghar Guardian alert: action failed, owner check needed"
        advice = "The shutoff command did not reduce flow. Check the supply manually."
    else:
        subject = "Ghar Guardian alert: collection gate fault"
        advice = "The collection gate reported a fault and collection was stopped. Inspect the gate."
    body = (f"Ghar Guardian (simulated home DEMO001)\nTime: {e['created_at']}\nEvent: {e['message']}\n"
            f"Evidence: {', '.join(e['evidence_codes']) or 'n/a'}\nRecommended: {advice}\n\n"
            "Demo prototype: sensors, pump and valves are simulated.")
    return subject, body


def _too_soon(state, now, gap):
    last = (state or {}).get("last_alert_at")
    if not last:
        return False
    try:
        return (now - datetime.fromisoformat(last)).total_seconds() < gap
    except ValueError:
        return False


def maybe_alert(new_events, state=None):
    """Returns extra timeline events describing alert attempts. Updates state['last_alert_at'] on success."""
    topic = os.getenv("ALERT_TOPIC_ARN")
    if not topic:
        return []
    gap = float(os.getenv("ALERT_MIN_INTERVAL_SECONDS", "300"))
    out = []
    for e in new_events:
        if e["event_type"] not in ALERT_EVENTS:
            continue
        now = datetime.now(timezone.utc)
        if _too_soon(state, now, gap):
            out.append(sm._ev("OWNER_ALERT_SKIPPED", "ALERTING",
                              "Owner alert skipped: rate limit (one alert email per few minutes).", action="SNS: RATE_LIMITED"))
            continue
        subject, body = _compose(e)
        try:
            _sns().publish(TopicArn=topic, Subject=subject, Message=body)
            if state is not None:
                state["last_alert_at"] = now.isoformat()
            out.append(sm._ev("OWNER_ALERT", "ALERTING", "Owner alert published to Amazon SNS (email).",
                              action="SNS: PUBLISHED"))
        except Exception as ex:
            print("SNS ERROR", repr(ex))
            out.append(sm._ev("OWNER_ALERT_FAILED", "ALERTING", "Owner alert could not be sent. Check SNS and CloudWatch logs.",
                              "MEDIUM", action="SNS: FAILED"))
    return out
