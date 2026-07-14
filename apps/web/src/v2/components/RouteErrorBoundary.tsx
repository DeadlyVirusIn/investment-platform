// Route-level error boundary (audit M7) — a crash inside one route must
// never white-screen the app. The boundary resets automatically on
// navigation (resetKey = pathname), offers retry + return-to-Discover,
// announces itself to screen readers, and logs BOUNDED technical context
// (name/message/stack prefixes only — never API payloads or secrets).

import { Component, useEffect, useRef, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { StatusPanel } from './ui/StatusPanel';

const MAX_LOG_CHARS = 600;

function boundedLog(pathname: string, error: unknown, componentStack?: string | null) {
  const name = error instanceof Error ? error.name : 'UnknownError';
  const message = (error instanceof Error ? error.message : String(error)).slice(0, MAX_LOG_CHARS);
  const stack = (componentStack ?? '').split('\n').slice(0, 8).join('\n');
  // eslint-disable-next-line no-console
  console.error(`[route-error] path=${pathname} ${name}: ${message}`, stack);
}

function FallbackContent({ pathname, onRetry }: { pathname: string; onRetry: () => void }) {
  const headingRef = useRef<HTMLDivElement>(null);
  // Move focus to the announcement so keyboard/SR users land on the
  // explanation instead of a silently emptied page.
  useEffect(() => { headingRef.current?.focus(); }, []);
  return (
    <main className="max-w-copy mx-auto px-5 py-16" aria-labelledby="route-error-title">
      <div ref={headingRef} tabIndex={-1} className="outline-none">
        <StatusPanel variant="error" title="This page hit a snag." role="alert">
          <span id="route-error-title">
            Something went wrong while drawing this screen — the rest of
            ArthOS is fine, and your practice portfolio data is safe (it
            lives on the server, not in this page). You can retry, or head
            back to Discover.
          </span>
        </StatusPanel>
      </div>
      <div className="flex items-center gap-4 mt-5 flex-wrap">
        <button
          type="button"
          onClick={onRetry}
          className="px-4 py-2 rounded-full font-semibold"
          style={{ fontSize: 13, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)' }}
        >
          Try this page again
        </button>
        <Link
          to="/discover"
          className="text-[13px] font-semibold"
          style={{ color: 'var(--brand)' }}
        >
          Back to Discover →
        </Link>
      </div>
      <p className="ink-fainter text-[11.5px] mt-6 tabular-nums">
        Route: {pathname}
      </p>
    </main>
  );
}

type BoundaryState = { hasError: boolean; retryCount: number };

class Boundary extends Component<
  { children: ReactNode; resetKey: string },
  BoundaryState
> {
  state: BoundaryState = { hasError: false, retryCount: 0 };

  static getDerivedStateFromError(): Partial<BoundaryState> {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: { componentStack?: string | null }) {
    boundedLog(this.props.resetKey, error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey: string }) {
    // Navigating away clears the failure — the next route gets a clean try.
    if (prev.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  retry = () => {
    this.setState((s) => ({ hasError: false, retryCount: s.retryCount + 1 }));
  };

  render() {
    if (this.state.hasError) {
      return <FallbackContent pathname={this.props.resetKey} onRetry={this.retry} />;
    }
    // retryCount keys the subtree so retry remounts it from scratch.
    return <div key={this.state.retryCount} className="contents">{this.props.children}</div>;
  }
}

// Dev-only fault injection: ?__crash=1 throws inside the boundary so the
// failure UX can be exercised in a real browser. Compiled out of prod
// behavior by the DEV check.
function DevCrash() {
  const location = useLocation();
  if (import.meta.env.DEV && new URLSearchParams(location.search).get('__crash') === '1') {
    throw new Error('dev-only injected crash (?__crash=1)');
  }
  return null;
}

/** Wrap the V2 route tree: failures stay inside the routed area, reset on
 *  navigation, and remount cleanly on retry. */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <Boundary resetKey={location.pathname}>
      <DevCrash />
      {children}
    </Boundary>
  );
}
