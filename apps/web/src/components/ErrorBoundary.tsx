import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
  info: ErrorInfo | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, info: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, info: null };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info });
    console.error('[ErrorBoundary]', error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="mt-4 rounded-md border border-negative/40 bg-negative/10 p-4 text-sm text-negative">
        <div className="font-semibold mb-1">
          {this.props.fallbackTitle ?? 'Page failed to render'}
        </div>
        <div className="text-xs font-mono text-text-secondary break-all">
          {this.state.error?.message ?? 'Unknown error'}
        </div>
        <div className="text-xs text-text-muted mt-2">
          The page crashed inside a child component. Check browser console for
          the stack trace. This fallback prevents a fully blank page.
        </div>
      </div>
    );
  }
}
