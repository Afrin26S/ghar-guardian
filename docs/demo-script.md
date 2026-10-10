# 3-minute demo script (aim for 2:45)
0:00 Hook: homes depend on tanks, pumps, monsoon water; nobody is home to interpret abnormal behavior.
0:15 Show dashboard: SIMULATED HOME badge, "AWS connected", architecture: Dashboard > API Gateway > Lambda > DynamoDB.
0:35 Activate Away Mode > Simulate Water Anomaly: evidence chips, STOP_PUMP, "probable anomaly, cause not confirmed".
1:05 Verification: 3.8 > 0.1 L/min, CONTAINED. Tick "Valve will fail", run again: ESCALATED.
1:25 Start RainSafe: gate closed during first flush, sample passes, gate opens, tank fills, closes at 100%.
1:55 Simulate Poor Sample: gate stays closed, REJECTED.
2:15 AWS proof (real, not a slide): DynamoDB items for HOME#DEMO001 + CloudWatch log line for the request.
2:40 Limits: simulated hardware, no leak localisation, demo thresholds are not drinking-water certification.
