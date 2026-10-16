import { useEffect, useState } from 'react';
import { getHealth } from '../api/client';

type Status = 'checking' | 'online' | 'offline';

/**
 * Backend connection badge for the header: pings GET /health.
 */
export function BackendStatus() {
  const [status, setStatus] = useState<Status>('checking');

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      getHealth()
        .then((res) => {
          if (!cancelled) setStatus(res.status === 'ok' ? 'online' : 'offline');
        })
        .catch(() => {
          if (!cancelled) setStatus('offline');
        });
    };
    check();
    const id = window.setInterval(check, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const label =
    status === 'online'
      ? 'Backend connected'
      : status === 'offline'
        ? 'Backend offline'
        : 'Checking backend…';

  return (
    <span
      className={`backend-status is-${status}`}
      role="status"
      aria-live="polite"
      data-testid="backend-status"
      data-status={status}
    >
      <span className="dot" aria-hidden="true" />
      {label}
    </span>
  );
}
