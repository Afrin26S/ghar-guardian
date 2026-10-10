export const litresAtRisk = (flowLpm, hours = 8) => Math.round(flowLpm * 60 * hours);

export function buildReport(decision, events) {
  const d = decision || {}, v = d.verification;
  const L = [
    "GHAR GUARDIAN INCIDENT REPORT (simulated home, DEMO001)",
    `Generated: ${new Date().toLocaleString()}`, "",
    `Incident: ${d.incident ? d.incident.replaceAll("_", " ").toLowerCase() : "none"}`,
    `Severity: ${d.severity ?? "n/a"}`,
    `Evidence: ${(d.evidence_codes || []).join(", ") || "n/a"}`,
    `Approved action: ${d.action ?? "n/a"}`,
  ];
  if (v) {
    L.push(`Verification: flow ${v.before} -> ${v.after} L/min`);
    L.push(`Estimated water at risk over 8 h: about ${litresAtRisk(v.before)} L (simulation estimate)`);
  }
  L.push(`Status: ${d.status ?? "n/a"}`, "", `Explanation: ${d.explanation ?? ""}`, "", "Recent events:");
  events.slice(0, 8).reverse().forEach((e) => L.push(`- ${new Date(e.created_at).toLocaleTimeString()} ${e.message}`));
  L.push("", "Limits: all sensors and actuators are simulated. This reports a probable water-system anomaly; the exact cause and location are not confirmed. Not a safety-certified controller.");
  return L.join("\n");
}
