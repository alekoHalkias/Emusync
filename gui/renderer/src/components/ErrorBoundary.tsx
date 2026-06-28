import React from "react";

type Props = { children: React.ReactNode };
type State = { error: Error | null; info: string };

/**
 * App-wide error boundary. Without one, any exception thrown during React render
 * unmounts the whole tree and leaves a blank white page (issue #270 follow-up).
 * This catches the error, keeps the window usable, shows the message + stack so
 * the underlying bug is visible, and offers a reload.
 */
export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, info: "" };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Surface it in the devtools console too.
    console.error("Renderer crash caught by ErrorBoundary:", error, info);
    this.setState({ info: info.componentStack ?? "" });
  }

  render(): React.ReactNode {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    return (
      <div style={{ padding: 24, fontFamily: "system-ui, sans-serif", color: "var(--text, #ddd)", maxHeight: "100vh", overflow: "auto" }}>
        <h2 style={{ marginTop: 0 }}>Something went wrong</h2>
        <p style={{ color: "var(--text-muted, #999)", fontSize: 13 }}>
          EmuSync hit an unexpected error. The details below help diagnose it.
        </p>
        <pre style={{
          whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12,
          background: "var(--panel, #1b1b1b)", border: "1px solid var(--border, #333)",
          borderRadius: 6, padding: 12, maxHeight: "40vh", overflow: "auto",
        }}>
          {error.message}
          {error.stack ? `\n\n${error.stack}` : ""}
          {info ? `\n\nComponent stack:${info}` : ""}
        </pre>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Reload</button>
          <button className="btn btn-ghost" onClick={() => this.setState({ error: null, info: "" })}>Dismiss</button>
        </div>
      </div>
    );
  }
}
