import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface RiskComparisonChartProps {
  costProbability: number | null;
  timeProbability: number | null;
}

/**
 * Side-by-side bar chart comparing cost-overrun vs time-overrun probabilities
 * for a single project.
 *
 * Both bars share the same 0-100% Y axis. They are overlapping risk estimates
 * - NOT mutually exclusive and NOT expected to sum to 100%. A null time
 * probability is shown as unavailable (bar omitted, never zero-filled).
 */
export function RiskComparisonChart({
  costProbability,
  timeProbability,
}: RiskComparisonChartProps) {
  const hasCost = costProbability != null && !Number.isNaN(costProbability);
  const hasTime = timeProbability != null && !Number.isNaN(timeProbability);

  const data = [
    {
      name: 'Cost overrun probability',
      value: hasCost ? costProbability! : 0,
      available: hasCost,
    },
    {
      name: 'Time overrun probability',
      value: hasTime ? timeProbability! : 0,
      available: hasTime,
    },
  ].filter((d) => d.available);

  if (data.length === 0) {
    return (
      <div className="risk-chart-wrap">
        <p className="muted">
          No risk probabilities are available for this project.
        </p>
      </div>
    );
  }

  return (
    <div className="risk-chart-wrap">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={data}
          margin={{ top: 24, right: 24, bottom: 36, left: 48 }}
          role="img"
          aria-label={
            data.length === 2
              ? 'Comparison of cost-overrun and time-overrun probabilities for the selected project'
              : data[0].name === 'Cost overrun probability'
              ? 'Cost-overrun probability for the selected project'
              : 'Time-overrun probability for the selected project'
          }
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11 }}
            interval={0}
            height={44}
            label={{
              value: 'Risk estimate',
              position: 'insideBottom',
              offset: 0,
              fontSize: 11,
            }}
          />
          <YAxis
            domain={[0, 100]}
            label={{
              value: 'Probability (%)',
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 11 },
            }}
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            content={({ active, payload }: any) => {
              if (active && payload && payload.length) {
                const item = payload[0].payload as {
                  name: string;
                  value: number;
                };
                return (
                  <div className="risk-tooltip">
                    <p className="muted">{item.name}</p>
                    <p style={{ fontWeight: 700 }}>
                      {item.value.toFixed(2)}%
                    </p>
                  </div>
                );
              }
              return null;
            }}
          />
          <Bar
            dataKey="value"
            radius={[4, 4, 0, 0]}
            fill="#2f6fb6"
          />
        </BarChart>
      </ResponsiveContainer>
      <p className="risk-chart-caption muted">
        Cost-overrun and time-overrun probabilities are overlapping risk
        estimates for the same project - they are not mutually exclusive and do
        not sum to 100%.{' '}
        {hasCost && !hasTime
          ? 'Time-overrun probability is unavailable for this project.'
          : !hasCost && hasTime
          ? 'Cost-overrun probability is unavailable for this project.'
          : ''}
      </p>
    </div>
  );
}
