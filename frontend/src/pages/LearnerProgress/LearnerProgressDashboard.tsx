import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
  { topic: 'Mastered', count: 5 },
  { topic: 'In Progress', count: 3 },
  { topic: 'Not Started', count: 2 },
];

export function LearnerProgressDashboard() {
  return (
    <main aria-label="Learner progress dashboard">
      <h1>Learner Progress</h1>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <XAxis dataKey="topic" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="count" fill="#4f46e5" />
        </BarChart>
      </ResponsiveContainer>
    </main>
  );
}
