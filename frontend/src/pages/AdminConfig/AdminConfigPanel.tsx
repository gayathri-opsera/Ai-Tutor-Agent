import { useEffect, useState } from 'react';

export function AdminConfigPanel() {
  const [configs, setConfigs] = useState<Array<{ key: string; value: unknown }>>([]);
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');

  useEffect(() => {
    fetch('/api/v1/admin/config?organization_id=default')
      .then((r) => r.json())
      .then((d) => setConfigs(d.configs || []));
  }, []);

  const save = async () => {
    await fetch(`/api/v1/admin/config/${key}?organization_id=default`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    });
    setConfigs((c) => [...c.filter((x) => x.key !== key), { key, value }]);
  };

  return (
    <main aria-label="Admin configuration panel">
      <h1>Admin Configuration</h1>
      <form onSubmit={(e) => { e.preventDefault(); save(); }}>
        <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="Config key" aria-label="Config key" />
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Config value" aria-label="Config value" />
        <button type="submit">Save</button>
      </form>
      <ul>{configs.map((c) => <li key={c.key}>{c.key}: {String(c.value)}</li>)}</ul>
    </main>
  );
}
