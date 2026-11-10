import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const COLORS: Record<string, string> = {
  P0: '#ef4444',
  P1: '#f97316',
  P2: '#eab308',
  P3: '#3b82f6',
  P4: '#9ca3af',
};

export default function PriorityChart({ distribution }: { distribution: Record<string, number> }) {
  const data = ['P0', 'P1', 'P2', 'P3', 'P4'].map((p) => ({
    name: p,
    count: distribution[p] || 0,
  }));

  return (
    <div className="bg-white rounded-lg border p-4">
      <h3 className="font-semibold mb-3">Priority Distribution</h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <XAxis dataKey="name" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={COLORS[entry.name]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
