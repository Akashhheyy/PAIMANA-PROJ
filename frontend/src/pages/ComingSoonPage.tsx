import { Construction } from 'lucide-react';

/**
 * Placeholder for routes that are navigation-only in Phase 9.2.
 * It intentionally shows NO data and fabricates nothing - the real pages
 * arrive in a later phase.
 */
export function ComingSoonPage({ title }: { title: string }) {
  return (
    <div className="page">
      <section className="card section">
        <div className="state-block">
          <Construction size={24} aria-hidden="true" />
          <h2>{title}</h2>
          <p className="muted">
            This page is planned for a later phase and is not implemented yet.
            Only the Overview dashboard is functional in this release.
          </p>
        </div>
      </section>
    </div>
  );
}
