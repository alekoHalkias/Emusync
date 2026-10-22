import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./styles.css";
import "./themes/default.css";

// Nothing in the app uses drag-and-drop. Suppress the native behaviour so click-dragging a
// card's art <img> can't start an OS drag (froze the app, #551) and a dropped file can't navigate the window.
for (const type of ["dragstart", "dragover", "drop"]) {
  window.addEventListener(type, (e) => e.preventDefault());
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
