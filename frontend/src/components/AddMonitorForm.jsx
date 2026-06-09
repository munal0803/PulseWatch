import { useState } from "react";

const API = "http://localhost:8000/api";

export default function AddMonitorForm() {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [urlError, setUrlError] = useState("");
  const [feedback, setFeedback] = useState({ message: "", ok: true });
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setUrlError("");
    setFeedback({ message: "", ok: true });

    if (!url.trim()) {
      setUrlError("URL is required.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${API}/monitors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), name: name.trim() }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      setUrl("");
      setName("");
      setFeedback({ message: "Monitor added!", ok: true });
    } catch (err) {
      setFeedback({ message: err.message, ok: false });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="add-form" onSubmit={handleSubmit}>
      <h2>Add Monitor</h2>
      <div className="form-row">
        <div className="form-field">
          <label htmlFor="url">URL *</label>
          <input
            id="url"
            type="text"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          {urlError && <span className="field-error">{urlError}</span>}
        </div>
        <div className="form-field">
          <label htmlFor="name">Name</label>
          <input
            id="name"
            type="text"
            placeholder="My Site"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Adding…" : "Add"}
        </button>
      </div>
      {feedback.message && (
        <p className={feedback.ok ? "success-text" : "error-text"}>{feedback.message}</p>
      )}
    </form>
  );
}
