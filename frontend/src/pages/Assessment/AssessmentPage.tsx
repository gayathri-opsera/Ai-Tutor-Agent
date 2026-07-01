import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useUser } from '../../auth/UserContext';
import { KB_API } from '../../config/api';

const ASSESSMENT_API = '/api/v1/assessments';
const LEARNER_API    = '/api/v1/learner';

interface Question { id: string; text: string; options: string[]; correct_index: number; }
interface Assessment { id: string; title: string; assessment_type: string; knowledge_base_id: string; questions: Question[]; }
interface Result { result_id: string; score: number; correct: number; total: number; percentage: number; }

// ────────────────────────────────────────────────────────────────────────────────
// Seed data helper — auto-create a sample assessment if none exist for a KB
// ────────────────────────────────────────────────────────────────────────────────
async function seedAssessment(kbId: string, kbName: string): Promise<string> {
  const res = await fetch(ASSESSMENT_API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: `${kbName} — Knowledge Check`,
      assessment_type: 'pre',
      knowledge_base_id: kbId,
      questions: [
        {
          id: crypto.randomUUID(),
          text: `What is the main topic covered in the "${kbName}" knowledge base?`,
          options: [kbName, 'Web development', 'Database design', 'None of the above'],
          correct_index: 0,
        },
        {
          id: crypto.randomUUID(),
          text: 'Which type of assessment is this?',
          options: ['Post-training', 'Pre-training', 'Certification', 'Practice'],
          correct_index: 1,
        },
        {
          id: crypto.randomUUID(),
          text: 'How confident are you with this topic before starting?',
          options: ['Very confident', 'Somewhat confident', 'Not very confident', 'Complete beginner'],
          correct_index: 3,
        },
      ],
    }),
  });
  const data = await res.json();
  return data.id;
}

// ────────────────────────────────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────────────────────────────────
export function AssessmentPage() {
  const { id: kbId }              = useParams<{ id: string }>();
  const { user }                  = useUser();
  const navigate                  = useNavigate();
  const [loading, setLoading]     = useState(true);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [answers, setAnswers]     = useState<Record<string, number>>({});
  const [result, setResult]       = useState<Result | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [kbName, setKbName]       = useState('');
  const [error, setError]         = useState('');

  const userId = user?.id ?? 'demo-user';

  useEffect(() => {
    if (!kbId) { navigate('/content'); return; }

    // load KB name
    fetch(`${KB_API}/${kbId}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setKbName(d.name ?? ''); })
      .catch(() => {});

    // load or create assessment
    fetch(`${ASSESSMENT_API}?knowledge_base_id=${kbId}`)
      .then(r => r.ok ? r.json() : { items: [] })
      .then(async ({ items }: { items: Assessment[] }) => {
        if (items.length > 0) {
          const full = await fetch(`${ASSESSMENT_API}/${items[0].id}`).then(r => r.json());
          setAssessment(full);
        } else {
          const newId = await seedAssessment(kbId, kbName || 'Knowledge Base');
          const full  = await fetch(`${ASSESSMENT_API}/${newId}`).then(r => r.json());
          setAssessment(full);
        }
        setLoading(false);
      })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, [kbId]);

  const handleAnswer = (qId: string, idx: number) => setAnswers(a => ({ ...a, [qId]: idx }));

  const handleSubmit = async () => {
    if (!assessment) return;
    const unanswered = assessment.questions.filter(q => answers[q.id] === undefined);
    if (unanswered.length > 0) { alert(`Please answer all questions (${unanswered.length} remaining)`); return; }

    setSubmitting(true);
    try {
      const res = await fetch(`${ASSESSMENT_API}/${assessment.id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, answers }),
      });
      const data = await res.json();
      setResult(data);

      // update learner profile topic
      await fetch(`${LEARNER_API}/topic?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: kbName || 'Knowledge Check',
          level: data.percentage >= 70 ? 'mastered' : 'in_progress',
          score: data.score,
          knowledge_base_id: kbId,
        }),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="container" style={{ paddingTop: 60, textAlign: 'center' }}>
        <div className="spinner" />
        <p className="text-muted mt-4">Loading assessment…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container" style={{ paddingTop: 60 }}>
        <div className="alert alert-error">{error}</div>
      </div>
    );
  }

  if (result) {
    const passed = result.percentage >= 70;
    return (
      <div>
        <div className="page-header">
          <div className="container"><h1>Assessment Complete</h1></div>
        </div>
        <div className="container" style={{ maxWidth: 600 }}>
          <div className="table-wrap" style={{ padding: 40, textAlign: 'center', marginTop: 32 }}>
            <div style={{ fontSize: '4rem', marginBottom: 16 }}>{passed ? '🎉' : '📖'}</div>
            <h2 style={{ fontSize: '2rem', marginBottom: 8 }}>{result.percentage.toFixed(0)}%</h2>
            <p className="text-muted mb-6">{result.correct} of {result.total} correct</p>
            <div style={{
              background: passed ? '#dcfce7' : '#fef9c3',
              color: passed ? '#166534' : '#854d0e',
              borderRadius: 12, padding: '16px 24px', marginBottom: 24,
            }}>
              {passed
                ? 'Great work! You\'ve demonstrated good understanding of this topic.'
                : 'Keep studying! Review the material and try again when you\'re ready.'}
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button className="btn btn-secondary" onClick={() => navigate(`/course/${kbId}`)}>Back to Course</button>
              <button className="btn btn-primary" onClick={() => navigate(`/chat`)}>Ask AI Tutor</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div className="container">
          <h1>{assessment?.title ?? 'Assessment'}</h1>
          <p>{kbName} · {assessment?.questions?.length ?? 0} questions · {assessment?.assessment_type} assessment</p>
        </div>
      </div>

      <div className="container" style={{ maxWidth: 720, paddingTop: 32, paddingBottom: 60 }}>
        {assessment?.questions.map((q, qi) => (
          <div key={q.id} className="table-wrap" style={{ padding: 24, marginBottom: 20 }}>
            <p style={{ fontWeight: 600, marginBottom: 16 }}>
              <span style={{ color: 'var(--brand)', marginRight: 8 }}>Q{qi + 1}.</span>
              {q.text}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {q.options.map((opt, oi) => {
                const selected = answers[q.id] === oi;
                return (
                  <label key={oi} style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                    borderRadius: 10, cursor: 'pointer',
                    border: `2px solid ${selected ? 'var(--brand)' : 'var(--border)'}`,
                    background: selected ? 'var(--brand-light)' : 'transparent',
                    transition: 'all 0.15s',
                  }}>
                    <input
                      type="radio"
                      name={q.id}
                      value={oi}
                      checked={selected}
                      onChange={() => handleAnswer(q.id, oi)}
                      style={{ accentColor: 'var(--brand)' }}
                    />
                    <span style={{ fontWeight: selected ? 600 : 400 }}>{opt}</span>
                  </label>
                );
              })}
            </div>
          </div>
        ))}

        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 8 }}>
          <button className="btn btn-secondary" onClick={() => navigate(-1)}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={submitting || Object.keys(answers).length < (assessment?.questions?.length ?? 0)}
          >
            {submitting ? 'Submitting…' : 'Submit Assessment'}
          </button>
        </div>
      </div>
    </div>
  );
}
