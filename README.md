# Ghar Guardian

A software-first household water digital twin for Environmental Hacks (Heat & Water track).
The home, sensors, pump, valve and water are **simulated**. The AWS backend is **real**.

Two workflows, one dashboard, one explainable event timeline:
1. **Away Mode / Water Incident Autopilot**: correlate flow, pump, tank trend, occupancy and duration; pick an allowlisted action (STOP_PUMP / CLOSE_INLET / MONITOR_AND_NOTIFY); verify with a follow-up sample (CONTAINED or ESCALATED).
2. **RainSafe**: first-flush diversion, configurable collection policy, tank-capacity-aware gate, automatic closure at 100%.

## Limits (honest)
- Does not locate leaks behind walls. It reports a *probable water-system anomaly*, cause not confirmed.
- Does not certify drinking water. Thresholds are demo policy values; "passed" means suitable for storage under demo policy.
- Bedrock is not used unless a real invocation is implemented and shown.

## Architecture
Dashboard (React/Vite) -> API Gateway HTTP API -> Lambda (policy + state machine) -> DynamoDB (`GharGuardianDemo`) + CloudWatch Logs.
`backend/src/policy.py` and `state_machine.py` are pure Python and unit-tested without AWS.

## Run locally (no AWS)
```
cd backend && python3 -m unittest discover -s tests -v
python3 local_server.py            # http://localhost:8787 (in-memory; UI shows "Local API, not AWS")
cd ../frontend && npm install && npm run dev
```

## Deploy to AWS (SAM)
```
cd backend && sam build && sam deploy --guided --stack-name ghar-guardian
# copy the ApiUrl output into frontend/.env.local as VITE_API_URL=...
```
The UI shows "AWS connected (DynamoDB)" only when the backend reports it actually stored data in DynamoDB.

## Credits
Built during Environmental Hacks. AI coding assistance: Claude (Anthropic). Libraries: React, Vite. Fonts: Bricolage Grotesque, Source Sans 3 (OFL).
