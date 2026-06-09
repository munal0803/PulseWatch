import { useEffect, useState } from "react";
import { collection, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";
import AddMonitorForm from "./components/AddMonitorForm";
import MonitorList from "./components/MonitorList";

export default function App() {
  const [monitors, setMonitors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const unsub = onSnapshot(
      collection(db, "monitors"),
      (snapshot) => {
        const docs = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
        setMonitors(docs);
        setLoading(false);
      },
      (err) => {
        setError("Failed to load monitors: " + err.message);
        setLoading(false);
      }
    );
    return unsub;
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Uptime Monitor</h1>
      </header>
      <main className="app-main">
        <AddMonitorForm />
        {loading && <p className="status-text">Loading monitors…</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && !error && <MonitorList monitors={monitors} />}
      </main>
    </div>
  );
}
