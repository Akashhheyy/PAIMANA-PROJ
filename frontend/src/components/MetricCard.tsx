import type { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  label: string;
  value: number | string;
  hint?: string;
  icon?: LucideIcon;
  tone?: 'default' | 'high' | 'medium' | 'low';
}

/**
 * Summary metric card. Values always come from API data - never hardcoded.
 */
export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'default',
}: MetricCardProps) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        {Icon && <Icon size={18} aria-hidden="true" />}
      </div>
      <p className="metric-value">{value}</p>
      {hint && <p className="metric-hint">{hint}</p>}
    </article>
  );
}
