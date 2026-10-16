import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ProgressBin } from '../api/types';

interface ProgressChartProps {
  bins: ProgressBin[];
  snapshotLabel: string;
}

/**
 * Graph 1: overall physical-progress distribution from the pre-binned
 * endpoint. All bins are rendered exactly as returned by the backend -
 * no histogram is recomputed client-side, and no trend line is drawn
 * (historical snapshots do not exist).
 */
export function ProgressChart({ bins, snapshotLabel }: ProgressChartProps) {
  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={320}>
        <BarChart
          data={bins}
          margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
          role="img"
          aria-label={`Physical progress distribution of projects, ${snapshotLabel} snapshot`}
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 12 }}
            interval={0}
            angle={-35}
            textAnchor="end"
            height={60}
            label={{
              value: 'Physical progress range (%)',
              position: 'insideBottom',
              offset: -6,
              fontSize: 12,
            }}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 12 }}
            label={{
              value: 'Number of projects',
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 12 },
            }}
          />
          <Tooltip
            formatter={(value) => [`${value} projects`, 'Count']}
            labelFormatter={(label) => `Progress ${label}%`}
          />
          <Bar dataKey="count" fill="#2f6fb6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
