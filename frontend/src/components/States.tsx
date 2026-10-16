import type { ReactNode } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

/** Accessible loading state for async data. */
export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <Loader2 className="spin" size={22} aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

/** Error state fed by the API client's ApiError messages. */
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-block state-error" role="alert">
      <AlertTriangle size={22} aria-hidden="true" />
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/** Empty state when a query returns zero rows. */
export function EmptyState({
  message = 'No results found.',
}: {
  message?: string;
}) {
  return (
    <div className="state-block" role="status">
      <p>{message}</p>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <LoadingState label={label} />;
}

/** Small wrapper used by pages for consistent section framing. */
export function Section({
  title,
  subtitle,
  children,
  actions,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="card section">
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
        {actions && <div className="section-actions">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
