// Real forecast from Open-Meteo (free, no key). Advisory only; never controls the gate.
const LAT = 20.4625, LON = 85.8828;
export const PLACE_NAME = "Cuttack, Odisha";
const HEAVY_MM = 20, HIGH_TANK = 80; // demo thresholds, not engineering values

export async function fetchForecast() {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}` +
    "&hourly=precipitation,precipitation_probability&forecast_days=2&timezone=GMT";
  const res = await fetch(url);
  if (!res.ok) throw new Error("Forecast service error");
  const h = (await res.json()).hourly;
  const now = Date.now();
  let mm = 0, maxProb = 0;
  h.time.forEach((t, i) => {
    const ts = new Date(t + "Z").getTime(); // times are GMT without a suffix
    if (ts >= now - 3600e3 && ts < now + 24 * 3600e3) {
      mm += h.precipitation[i] || 0;
      maxProb = Math.max(maxProb, h.precipitation_probability?.[i] || 0);
    }
  });
  return { mm: Math.round(mm * 10) / 10, maxProb };
}

export function advisory(f, tank) {
  if (!f) return null;
  if (f.mm >= HEAVY_MM && tank >= HIGH_TANK)
    return { level: "warn", text: `Heavy rain forecast (${f.mm} mm in 24 h) and the tank is at ${tank}%. Little headroom: use stored water before the rain.` };
  if (f.mm >= HEAVY_MM)
    return { level: "ok", text: `Heavy rain forecast (${f.mm} mm in 24 h). The tank has ${100 - tank}% headroom for collection.` };
  if (f.mm >= 2)
    return { level: "ok", text: `Light rain possible (${f.mm} mm in 24 h). RainSafe is on standby.` };
  return { level: "ok", text: `No significant rain forecast (${f.mm} mm in 24 h). RainSafe stays on standby.` };
}
