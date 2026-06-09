import { formatDistanceToNow } from "date-fns";
import StatusBadge from "./StatusBadge";

const API = "http://localhost:8000/api";

function statusOrder(status) {
  if (status === "down") return 0;
  if (status === "up") return 1;
  return 2;
}

function formatCheckedAt(value) {
  if (!value) return "Never";
  try {
    const date = value.toDate ? value.toDate() : new Date(value);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return "Unknown";
  }
}

async function deleteMonitor(id) {
  await fetch(`${API}/monitors/${id}`, { method: "DELETE" });
}

export default function MonitorList({ monitors }) {
  if (!monitors.length) {
    return <p className="empty-text">No monitors yet. Add one above.</p>;
  }

  const sorted = [...monitors].sort(
    (a, b) => statusOrder(a.lastStatus) - statusOrder(b.lastStatus)
  );

  return (
    <div className="monitor-list">
      {sorted.map((m) => (
        <div key={m.id} className="monitor-card">
          <div className="monitor-info">
            <div className="monitor-name">{m.name || m.url}</div>
            {m.name && <div className="monitor-url">{m.url}</div>}
          </div>
          <div className="monitor-meta">
            <StatusBadge status={m.lastStatus} />
            <span className="monitor-rt">
              {m.lastResponseTime != null ? `${m.lastResponseTime} ms` : "—"}
            </span>
            <span className="monitor-checked">{formatCheckedAt(m.lastCheckedAt)}</span>
          </div>
          <button
            className="btn-delete"
            onClick={() => deleteMonitor(m.id)}
            title="Delete monitor"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  );
}
