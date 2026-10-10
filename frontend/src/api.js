const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8787").replace(/\/$/, "");
export const API_HOST = new URL(BASE).host;
const HOME = "DEMO001";

async function call(path, opts) {
  let res;
  try { res = await fetch(BASE + path, opts); }
  catch { throw new Error(`Cannot reach ${API_HOST}. Check the API URL, CORS origin and that the backend is running.`); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.message || `Request failed (${res.status})`);
  return data;
}
export const getSnapshot = () => call(`/snapshot?home_id=${HOME}`);
export const sendEvent = (event_type, params = {}) =>
  call("/event", { method: "POST", headers: { "Content-Type": "application/json" },
                   body: JSON.stringify({ home_id: HOME, event_type, params }) });
