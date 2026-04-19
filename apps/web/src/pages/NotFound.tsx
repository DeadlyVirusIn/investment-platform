import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-surface text-center px-4">
      <p className="text-6xl font-bold text-surface-border">404</p>
      <p className="mt-3 text-text-secondary text-lg">Page not found</p>
      <p className="mt-1 text-text-muted text-sm max-w-sm">
        The route you requested doesn't exist in this application.
      </p>
      <Link
        to="/dashboard"
        className="mt-6 btn-primary"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
