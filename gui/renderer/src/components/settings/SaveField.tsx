// Labelled text input with its own Save button and Saved/error feedback.
// `onSave` resolves to an error message, or nothing on success.
import React, { useState } from "react";

type Props = {
  label: React.ReactNode;
  value: string;
  onChange: (v: string) => void;
  onSave: () => Promise<string | void>;
  placeholder?: string;
};

export default function SaveField({ label, value, onChange, onSave, placeholder }: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  async function save(): Promise<void> {
    setBusy(true);
    const err = await onSave();
    setBusy(false);
    if (err) { setError(err); return; }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
        <div className="input-group" style={{ flex: 1 }}>
          <label>{label}</label>
          <input
            type="text"
            value={value}
            onChange={(e) => { onChange(e.target.value); setSaved(false); setError(""); }}
            onKeyDown={(e) => { if (e.key === "Enter") save(); }}
            placeholder={placeholder}
          />
        </div>
        <button className="btn btn-ghost" onClick={save} disabled={busy} style={{ flexShrink: 0 }}>
          {saved ? "Saved" : busy ? <span className="spinner" /> : "Save"}
        </button>
      </div>
      {error && <span className="error-msg" style={{ display: "block", marginTop: 4 }}>{error}</span>}
    </div>
  );
}
