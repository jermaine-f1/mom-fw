import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dashboard render error:", error, info);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="p-6">
        <div className="max-w-3xl mx-auto bg-red-900/30 border border-red-600/50 rounded-xl p-6 text-red-200">
          <div className="font-bold text-red-300 text-lg mb-2">
            Dashboard crashed while rendering
          </div>
          <div className="text-sm mb-3">
            {error.message || String(error)}
          </div>
          <div className="text-xs text-red-200/70">
            Check the browser console for a stack trace. Reload after
            regenerating <code className="mono">public/data.json</code>, or
            open an issue if it reproduces.
          </div>
        </div>
      </div>
    );
  }
}
