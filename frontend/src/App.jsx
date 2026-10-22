import React, { useEffect, useRef, useState } from "react";
import { getSnapshot, sendEvent, API_HOST } from "./api.js";
import { fetchForecast, advisory, PLACE_NAME } from "./forecast.js";
import { buildReport, litresAtRisk } from "./report.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LABEL = {
  IDLE: "Idle", FIRST_FLUSH: "First flush diverting", QUALITY_CHECK: "Checking sample",
  COLLECTING: "Collecting", TANK_FULL: "Tank full, gate closed", REJECTED: "Sample rejected, gate closed",
  SENSOR_FAULT: "Sensor fault, gate closed", ACTUATOR_FAULT: "Gate fault, collection stopped",
};
const SAMPLE_LABEL = { PASSED: "Passed configured collection policy", FAILED: "Failed configured collection policy",
                       SENSOR_FAULT: "Missing readings" };

function Twin({ s }) {
  const level = s.tank_level_percent, h = 150 * level / 100;
  const gateColor = { OPEN: "var(--ok)", CLOSED: "var(--ink)", FAULT: "var(--bad)" }[s.gate_state];
  const raining = s.rain_state === "RAINING";
  return (
    <svg viewBox="0 0 360 330" className="twin" role="img" aria-label="Simulated home water system">
      <rect x="10" y="10" width="340" height="30" rx="3" className="roof" />
      {raining && [40, 90, 140, 190, 240, 290].map((x, i) => (
        <line key={x} x1={x} y1="46" x2={x - 6} y2="70" className="rain" style={{ animationDelay: `${i * 0.15}s` }} />))}
      <text x="18" y="30" className="small">Roof catchment</text>
      <rect x="20" y="85" width="120" height="24" rx="3" className="box" />
      <text x="28" y="101" className="small">Fixed mesh / filter</text>
      <rect x="20" y="125" width="120" height="30" rx="3" className="box" />
      <text x="28" y="144" className="small">{s.rain_safe_state === "FIRST_FLUSH" ? "First flush: diverting" : "First-flush diverter"}</text>
      <circle cx="80" cy="190" r="13" fill={gateColor} />
      <text x="100" y="186" className="small">Collection gate</text>
      <text x="100" y="202" className="strong">{s.gate_state}</text>
      <rect x="200" y="110" width="120" height="156" rx="6" className="tank" />
      <rect x="201" y={265 - h} width="118" height={h} className="water" />
      <text x="260" y="196" textAnchor="middle" className="level">{level}%</text>
      <text x="260" y="286" textAnchor="middle" className="small">Storage tank</text>
      <rect x="20" y="236" width="120" height="30" rx="3" className="box" />
      <text x="28" y="255" className="small">Pump: {s.pump_state}</text>
      <rect x="20" y="276" width="120" height="30" rx="3" className="box" />
      <text x="28" y="295" className="small">Supply inlet: {s.inlet_state}</text>
      <text x="200" y="316" className="small">Flow {s.water_flow_lpm.toFixed(1)} L/min</text>
    </svg>
  );
}

export default function App() {
  const [s, setS] = useState(null);
  const [events, setEvents] = useState([]);
  const [decision, setDecision] = useState(null);
  const [storage, setStorage] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [anomaly, setAnomaly] = useState("PUMP_NO_RISE");
  const [forecast, setForecast] = useState(undefined); // undefined = loading, null = unavailable
  const [copied, setCopied] = useState(false);
  const faultRef = useRef(false);

  useEffect(() => {
    getSnapshot().then((d) => { setS(d.state); setEvents(d.events); setStorage(d.storage); setDecision(d.state.last_decision || null); })
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => { fetchForecast().then(setForecast).catch(() => setForecast(null)); }, []);

  async function run(type, params) {
    const d = await sendEvent(type, params);
    setErr(null); setS(d.state); setStorage(d.storage);
    setEvents((old) => [...d.new_events.slice().reverse(), ...old]);
    if (d.decision) setDecision(d.decision);
    return d;
  }
  async function guard(fn) {
    setBusy(true);
    try { await fn(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  const rain = (profile) => guard(async () => {
    setDecision(null); faultRef.current = false;
    await run("START_RAIN"); await sleep(2200);
    await run("FIRST_FLUSH_DONE"); await sleep(1800);
    let d = await run("SUBMIT_SAMPLE", { profile });
    while (d.state.rain_safe_state === "COLLECTING") {
      await sleep(1100);
      if (faultRef.current) { await run("SIMULATE_GATE_FAULT"); break; }
      d = await run("FILL_TICK");
    }
  });

  if (!s) return <main className="boot">{err ? <p className="err">{err}</p> : <p>Connecting to the water system…</p>}</main>;
  const away = s.mode === "AWAY";
  const live = storage === "dynamodb";
  const v = decision?.verification;
  const sample = s.last_sample;
  const adv = advisory(forecast, s.tank_level_percent);
  const copyReport = async () => {
    try { await navigator.clipboard.writeText(buildReport(decision, events)); setCopied(true); }
    catch { setCopied("failed"); }
    setTimeout(() => setCopied(false), 1800);
  };
  const litres = v ? litresAtRisk(v.before).toLocaleString("en-IN") : null;

  return (
    <main>
      <header className="top">
        <h1>Ghar Guardian</h1>
        <span className="tag">Simulated home</span>
        <span className={`tag ${away ? "away" : ""}`}>{away ? "Away Mode" : "Home Mode"}</span>
        <span className={`tag ${live ? "ok" : "warn"}`} title={API_HOST}>
          {live ? "AWS connected (DynamoDB)" : "Local API, not AWS"}
        </span>
      </header>

      {err && <p className="err" role="alert">Cloud error: {err}</p>}

      <section className="controls" aria-label="Scenario controls">
        <button disabled={busy} onClick={() => guard(() => run(away ? "ACTIVATE_HOME" : "ACTIVATE_AWAY"))}>
          {away ? "Return to Home Mode" : "Activate Away Mode"}
        </button>
        <select disabled={busy} value={anomaly} onChange={(e) => setAnomaly(e.target.value)} aria-label="Anomaly type">
          <option value="PUMP_NO_RISE">Pump on, tank not rising</option>
          <option value="LEAK_FLOW">Flow with pump off</option>
        </select>
        <button className="primary" disabled={busy} onClick={() => guard(() => run("SIMULATE_WATER_ANOMALY", { anomaly_type: anomaly }))}>
          Simulate Water Anomaly
        </button>
        <label className="chk"><input type="checkbox" disabled={busy} checked={s.valve_failure}
          onChange={(e) => guard(() => run("SET_VALVE_FAILURE", { enabled: e.target.checked }))} /> Valve will fail</label>
        <span className="sep" />
        <button className="primary" disabled={busy} onClick={() => rain("GOOD")}>Start RainSafe</button>
        <button disabled={busy} onClick={() => rain("POOR")}>Simulate Poor Sample</button>
        <button disabled={busy} onClick={() => rain("MISSING")}>Simulate Missing Sensor</button>
        <button disabled={!(busy && s.rain_safe_state === "COLLECTING")} onClick={() => { faultRef.current = true; }}>Simulate Gate Fault</button>
        <button disabled={busy} onClick={() => guard(async () => { await run("RESET"); setDecision(null); })}>Reset Scenario</button>
      </section>

      <div className="grid">
        <section className="panel" aria-label="Home digital twin">
          <h2>Home digital twin</h2>
          <Twin s={s} />
        </section>

        <section className="panel" aria-label="Guardian control center">
          <h2>Guardian control center</h2>
          <dl>
            <dt>RainSafe</dt><dd>{LABEL[s.rain_safe_state]}</dd>
            {sample && (<><dt>Sample</dt><dd>pH {sample.ph ?? "–"} · {sample.turbidity_ntu ?? "–"} NTU · {sample.tds_ppm ?? "–"} ppm TDS<br />
              <strong className={sample.result === "PASSED" ? "okt" : "badt"}>{SAMPLE_LABEL[sample.result]}</strong></dd></>)}
            <dt>Water incident</dt>
            <dd>{decision ? (decision.incident ? decision.incident.replaceAll("_", " ").toLowerCase() : "none (normal use)") : "none"}
              {decision && <span className={`sev ${decision.severity}`}> {decision.severity}</span>}</dd>
            {decision && (<>
              <dt>Evidence</dt>
              <dd className="chips">{decision.evidence_codes.map((c) => <span key={c} className="chip">{c}</span>)}</dd>
              <dt>Approved action</dt><dd>{decision.action}</dd>
              {v && (<><dt>Verification</dt>
                <dd>{v.before} → {v.after} L/min · <strong className={v.result === "VERIFIED" ? "okt" : "badt"}>{decision.status}</strong></dd></>)}
              {v && (<><dt>Water at risk</dt><dd>{v.result === "VERIFIED"
                ? `About ${litres} L kept from running for 8 h (simulation estimate).`
                : `About ${litres} L could be lost over 8 h at this flow (simulation estimate). Owner action needed.`}</dd></>)}
              <dt>Why</dt><dd>{decision.explanation}</dd>
              {decision.incident && (<><dt>Report</dt><dd><button onClick={copyReport}>
                {copied === true ? "Copied" : copied === "failed" ? "Copy failed" : "Copy incident report"}</button></dd></>)}
            </>)}
          </dl>
          <p className="note">Everything in the home is simulated; the backend is real. Thresholds are demo policy values,
            not a drinking-water standard. Passing means "suitable for storage under demo policy", not "safe to drink". This is a shared public sandbox, so click Reset Scenario before you start.</p>
        </section>
      </div>

      <section className="panel" aria-label="Rain forecast advisory">
        <h2>Rain forecast advisory: {PLACE_NAME}</h2>
        {forecast === undefined ? <p>Loading forecast…</p>
          : forecast === null ? <p className="note">Forecast unavailable (offline or blocked). The demo continues with simulated rain.</p>
          : <p className={adv.level === "warn" ? "badt" : ""}>{adv.text}</p>}
        <p className="note">Real forecast data from Open-Meteo.com (CC BY 4.0). Advisory only: it never controls the gate.
          "Start RainSafe" uses simulated rain.</p>
      </section>

      <section className="panel timeline" aria-label="Event timeline">
        <h2>Event timeline</h2>
        {events.length === 0 ? <p className="note">No events yet. Activate Away Mode or start RainSafe.</p> : (
          <div className="scroll"><table>
            <thead><tr><th>Time</th><th>Event</th><th>Evidence</th><th>Action</th><th>Outcome</th></tr></thead>
            <tbody>{events.map((e) => (
              <tr key={e.event_id}>
                <td>{new Date(e.created_at).toLocaleTimeString()}</td>
                <td>{e.message}</td>
                <td>{e.evidence_codes.join(", ")}</td>
                <td>{e.action_status || e.decision}</td>
                <td className={e.verification_status === "ESCALATED" ? "badt" : e.verification_status === "CONTAINED" ? "okt" : ""}>{e.verification_status}</td>
              </tr>))}</tbody>
          </table></div>)}
      </section>
    </main>
  );
}
