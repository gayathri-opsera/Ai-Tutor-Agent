import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

export function KnowledgeBaseList() {
  const [items, setItems] = useState<Array<{ id: string; name: string }>>([]);

  useEffect(() => {
    fetch('/api/v1/content-mgmt/knowledge-bases?organization_id=default')
      .then((r) => r.json())
      .then((d) => setItems(d.items || []))
      .catch(() => setItems([]));
  }, []);

  return (
    <main aria-label="Knowledge base list">
      <h1>Knowledge Bases</h1>
      <Link to="/content/upload">Upload Document</Link>
      <ul role="list">
        {items.map((kb) => (
          <li key={kb.id}>{kb.name}</li>
        ))}
      </ul>
    </main>
  );
}
