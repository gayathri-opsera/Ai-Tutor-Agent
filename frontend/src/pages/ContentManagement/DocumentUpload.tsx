import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export function DocumentUpload() {
  const [progress, setProgress] = useState(0);
  const [kbId, setKbId] = useState('default-kb');
  const navigate = useNavigate();

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setProgress(10);
    const form = new FormData();
    form.append('file', file);
    form.append('knowledge_base_id', kbId);
    setProgress(50);
    const resp = await fetch('/api/v1/content/upload', { method: 'POST', body: form });
    setProgress(100);
    if (resp.ok) {
      const data = await resp.json();
      navigate(`/content/status/${data.id}`);
    }
  };

  return (
    <main aria-label="Document upload">
      <h1>Upload Document</h1>
      <label htmlFor="kb-id">Knowledge Base ID</label>
      <input id="kb-id" value={kbId} onChange={(e) => setKbId(e.target.value)} aria-label="Knowledge base ID" />
      <input type="file" accept=".pdf,.docx" onChange={handleUpload} aria-label="Choose file" />
      <progress value={progress} max={100} aria-label="Upload progress">{progress}%</progress>
    </main>
  );
}
