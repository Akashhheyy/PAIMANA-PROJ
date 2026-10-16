import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MetricCard } from '../components/MetricCard';
import { ErrorState, LoadingState } from '../components/States';

describe('MetricCard', () => {
  it('renders label, value and hint from props (no hardcoded data)', () => {
    render(
      <MetricCard
        label="Total projects"
        value={1981}
        hint="April 2026 snapshot"
      />,
    );
    expect(screen.getByText('Total projects')).toBeInTheDocument();
    expect(screen.getByText('1981')).toBeInTheDocument();
    expect(screen.getByText('April 2026 snapshot')).toBeInTheDocument();
  });

  it('renders an em dash for missing numeric values', () => {
    render(<MetricCard label="Mean" value="—" />);
    expect(screen.getByText('Mean')).toBeInTheDocument();
  });
});

describe('States', () => {
  it('loading state is announced to assistive tech', () => {
    render(<LoadingState label="Loading dashboard data…" />);
    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading dashboard data…',
    );
  });

  it('error state shows the message and retry button', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Backend is unreachable." onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Backend is unreachable.');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
