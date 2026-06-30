export function AdminMonitoringDashboard() {
  const metrics = {
    llm_tokens: 125000,
    cache_hit_rate: 0.72,
    flagged_transcriptions: [
      { id: 't1', confidence: 0.45, filename: 'lecture.mp4' },
      { id: 't2', confidence: 0.38, filename: 'intro.wav' },
    ],
  };

  return (
    <main aria-label="Admin monitoring dashboard">
      <h1>Monitoring</h1>
      <section aria-label="LLM usage">
        <h2>LLM Token Usage</h2>
        <p>{metrics.llm_tokens.toLocaleString()} tokens</p>
      </section>
      <section aria-label="Cache hit rate">
        <h2>Cache Hit Rate</h2>
        <p>{(metrics.cache_hit_rate * 100).toFixed(1)}%</p>
      </section>
      <section aria-label="Flagged transcriptions">
        <h2>Flagged Transcriptions</h2>
        <ul>
          {metrics.flagged_transcriptions.map((t) => (
            <li key={t.id}>{t.filename} — confidence: {t.confidence}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
