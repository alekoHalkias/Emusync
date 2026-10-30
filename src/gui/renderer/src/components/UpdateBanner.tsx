import React, { useCallback, useEffect, useState } from "react";
import { useUpdater } from "./useUpdater";
import { WarningIcon } from "./icons";

export default function UpdateBanner(): React.ReactElement | null {
  const { status, releaseVersion, errorMessage, checkForUpdate, downloadUpdate, installUpdate } =
    useUpdater();
  const [dismissed, setDismissed] = useState(false);

  // Auto-check on mount
  useEffect(() => {
    checkForUpdate();
  }, [checkForUpdate]);

  // Auto-dismiss idle after a short delay
  useEffect(() => {
    if (status === "idle" && dismissed) {
      const id = setTimeout(() => setDismissed(false), 30000);
      return () => clearTimeout(id);
    }
  }, [status, dismissed]);

  if (status === "idle" && dismissed) return null;

  if (status === "error") {
    return (
      <div
        style={{
          background: "var(--surface2)",
          color: "var(--text-muted)",
          fontSize: 12,
          padding: "8px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span>
          <WarningIcon /> Update check failed: {errorMessage}
        </span>
        <button
          className="btn btn-ghost"
          style={{ fontSize: 11, padding: "2px 8px" }}
          onClick={() => checkForUpdate()}
        >
          Retry
        </button>
      </div>
    );
  }

  if (status === "update-available") {
    return (
      <div
        style={{
          background: "var(--bg)",
          color: "var(--text)",
          fontSize: 12,
          padding: "8px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span>
          <strong>Update available</strong> {releaseVersion}
          {releaseNotes && (
            <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>
              (click download for details)
            </span>
          )}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            className="btn btn-primary"
            style={{ fontSize: 11, padding: "3px 10px" }}
            onClick={() => {
              downloadUpdate();
            }}
          >
            Download
          </button>
          <button
            className="btn btn-ghost"
            style={{ fontSize: 11, padding: "3px 8px" }}
            onClick={() => setDismissed(true)}
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  if (status === "update-downloaded") {
    return (
      <div
        style={{
          background: "var(--bg)",
          color: "var(--text)",
          fontSize: 12,
          padding: "8px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span>
          <strong>Update ready</strong> {releaseVersion} — restart to install
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            className="btn btn-primary"
            style={{ fontSize: 11, padding: "3px 10px" }}
            onClick={() => installUpdate()}
          >
            Install & Restart
          </button>
          <button
            className="btn btn-ghost"
            style={{ fontSize: 11, padding: "3px 8px" }}
            onClick={() => setDismissed(true)}
          >
            Later
          </button>
        </div>
      </div>
    );
  }

  return null;
}
