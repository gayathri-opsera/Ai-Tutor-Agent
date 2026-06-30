import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

export function DocumentStatus() {
  const { id } = useParams();
  const [status, setStatus] = useState('uploading');

  useEffect(() => {
    if (!id) return;
    const poll = setInterval(async () => {
      const resp = await fetch(`/api/v1/content/${id}/status`);
      if (resp.ok) {
        const data = await resp.json();
        setStatus(data.status);
        if (data.status === 'active' || data.status === 'error') clearInterval(poll);
      }
    }, 2000);
    return () => clearInterval(poll);
  }, [id]);

  return (
    <main aria-label="Document status">
      <h1>Document Status</h1>
      <p>Status: <strong>{status}</strong></p>
    </main>
  );
}
