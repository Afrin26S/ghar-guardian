"""Owner alerts via Amazon SNS (email). Optional: active only when ALERT_TOPIC_ARN is set.
A failure to send is logged as a timeline event and never breaks the request."""
import os

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


def maybe_alert(new_events):
    """Returns extra timeline events (0 or more) describing alert attempts."""
    topic = os.getenv("ALERT_TOPIC_ARN")
    if not topic:
        return []
    out = []
    for e in new_events:
        if e["event_type"] not in ALERT_EVENTS:
            continue
        subject, body = _compose(e)
        try:
            _sns().publish(TopicArn=topic, Subject=subject, Message=body)
            out.append(sm._ev("OWNER_ALERT", "ALERTING", "Owner alert published to Amazon SNS (email).",
                              action="SNS: PUBLISHED"))
        except Exception as ex:
            print("SNS ERROR", repr(ex))
            out.append(sm._ev("OWNER_ALERT_FAILED", "ALERTING", "Owner alert could not be sent. Check SNS and CloudWatch logs.",
                              "MEDIUM", action="SNS: FAILED"))
    return out
