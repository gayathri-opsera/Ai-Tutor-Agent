import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useUser } from '../../auth/UserContext';
import { KB_API } from '../../config/api';

const ASSESSMENT_API = '/api/v1/assessments';
const LEARNER_API    = '/api/v1/learner';

// ── Types ─────────────────────────────────────────────────────────────────────
interface Question {
  id: string;
  text: string;
  question_type: string;
  options: string[];
}

interface Assessment {
  id: string;
  title: string;
  assessment_type: string;
  knowledge_base_id: string;
  questions: Question[];
}

interface QuestionFeedback {
  question_id: string;
  question_text: string;
  is_correct: boolean;
  submitted_index: number | null;
  correct_index: number;
  correct_answer: string;
  submitted_answer: string | null;
}

interface Result {
  result_id: string;
  score: number;
  correct: number;
  total: number;
  percentage: number;
  feedback_per_question: QuestionFeedback[];
}

interface Comparison {
  pre_score: number | null;
  post_score: number | null;
  improvement_percentage: number | null;
  pre_attempts: number;
  post_attempts: number;
  has_improvement: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
async function fetchOrSeedAssessment(kbId: string, kbName: string): Promise<Assessment> {
  const listResp = await fetch(`${ASSESSMENT_API}?knowledge_base_id=${kbId}`);
  const { items } = await listResp.json() as { items: { id: string; assessment_type: string }[] };

  if (items.length > 0) {
    const takeResp = await fetch(`${ASSESSMENT_API}/${items[0].id}/take`);
    return takeResp.json();
  }

  // No assessment yet — seed a starter one
  const created = await fetch(ASSESSMENT_API, {
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
          question_type: 'multiple_choice',
          options: [kbName, 'Web development', 'Database design', 'None of the above'],
          correct_index: 0,
        },
        {
          id: crypto.randomUUID(),
          text: 'What type of assessment is this?',
          question_type: 'multiple_choice',
          options: ['Post-training', 'Pre-training', 'Certification', 'Practice'],
          correct_index: 1,
        },
        {
          id: crypto.randomUUID(),
          text: 'How confident are you with this topic before starting?',
          question_type: 'multiple_choice',
          options: ['Very confident', 'Somewhat confident', 'Not very confident', 'Complete beginner'],
          correct_index: 3,
        },
      ],
    }),
  }).then(r => r.json()) as { id: string };

  const takeResp = await fetch(`${ASSESSMENT_API}/${created.id}/take`);
  return takeResp.json();
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ResultBadge({ feedback }: { feedback: QuestionFeedback[] }) {
  const correct = feedback.filter(f => f.is_correct).length;
  const pct = Math.round((correct / feedback.length) * 100);
  return (
    <div style={{
      display: 'flex', gap: 6, alignItems: 'center', fontSize: '0.78rem',
      color: pct >= 70 ? '#166534' : '#92400e',
    }}>
      <span>{correct}/{feedback.length}</span>
      <span style={{ fontWeight: 700 }}>{pct}%</span>
    </div>
  );
}

function ImprovementBanner({ comparison }: { comparison: Comparison }) {
  if (comparison.pre_score === null || comparison.post_score === null) return null;
  const gained = comparison.improvement_percentage ?? 0;
  const color = gained >= 0 ? { bg: '#dcfce7', border: '#86efac', text: '#166534' }
                            : { bg: '#fee2e2', border: '#fca5a5', text: '#991b1b' };
  return (
    <div style={{
      margin: '0 0 28px', padding: '14px 20px', borderRadius: 10,
      background: color.bg, border: `1px solid ${color.border}`,
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <span style={{ fontSize: '1.8rem' }}>{gained >= 0 ? '📈' : '📉'}</span>
      <div>
        <p style={{ fontWeight: 700, marginBottom: 2, color: color.text }}>
          {gained >= 30
            ? 'Excellent improvement!'
            : gained >= 10
            ? 'Good progress!'
            : gained >= 0
            ? 'Slight improvement'
            : 'No improvement yet — keep studying!'}
        </p>
        <p style={{ fontSize: '0.82rem', color: color.text }}>
          Pre-training: {comparison.pre_score.toFixed(0)}% → Post-training: {comparison.post_score.toFixed(0)}%
          {' '}({gained >= 0 ? '+' : ''}{gained.toFixed(0)} points)
        </p>
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export function AssessmentPage() {
  const { id: kbId }                          = useParams<{ id: string }>();
  const { user }                              = useUser();
  const navigate                              = useNavigate();
  const [loading, setLoading]                 = useState(true);
  const [assessment, setAssessment]           = useState<Assessment | null>(null);
  const [answers, setAnswers]                 = useState<Record<string, number>>({});
  const [result, setResult]                   = useState<Result | null>(null);
  const [comparison, setComparison]           = useState<Comparison | null>(null);
  const [submitting, setSubmitting]           = useState(false);
  const [generating, setGenerating]           = useState(false);
  const [kbName, setKbName]                   = useState('');
  const [error, setError]                     = useState('');
  const [showFeedback, setShowFeedback]       = useState(false);

  const userId = user?.id ?? 'demo-user';

  useEffect(() => {
    if (!kbId) { navigate('/content'); return; }

    const load = async () => {
      try {
        const [kbData, assess] = await Promise.all([
          fetch(`${KB_API}/${kbId}`).then(r => r.ok ? r.json() : null),
          fetchOrSeedAssessment(kbId, 'Knowledge Base'),
        ]);
        if (kbData?.name) setKbName(kbData.name);
        setAssessment(assess);

        // Load pre/post comparison for this user+KB
        const cmpResp = await fetch(
          `${ASSESSMENT_API}/compare/${userId}?knowledge_base_id=${kbId}`
        );
        if (cmpResp.ok) setComparison(await cmpResp.json());
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [kbId]);

  const handleAnswer = (qId: string, idx: number) =>
    setAnswers(a => ({ ...a, [qId]: idx }));

  const handleSubmit = async () => {
    if (!assessment) return;
    const unanswered = assessment.questions.filter(q => answers[q.id] === undefined);
    if (unanswered.length > 0) {
      alert(`Please answer all questions (${unanswered.length} remaining)`);
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${ASSESSMENT_API}/${assessment.id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, answers }),
      });
      const data: Result = await res.json();
      setResult(data);
      setShowFeedback(false);

      // Update learner profile with topic progress
      await fetch(`${LEARNER_API}/topic?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: kbName || 'Knowledge Check',
          level: data.percentage >= 70 ? 'mastered' : 'in_progress',
          score: data.score,
          knowledge_base_id: kbId,
        }),
      }).catch(() => {});

      // Refresh comparison banner
      const cmpResp = await fetch(
        `${ASSESSMENT_API}/compare/${userId}?knowledge_base_id=${kbId}`
      );
      if (cmpResp.ok) setComparison(await cmpResp.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleGenerateAI = async () => {
    if (!kbId) return;
    setGenerating(true);
    setError('');
    try {
      const res = await fetch(`${ASSESSMENT_API}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          knowledge_base_id: kbId,
          topic: kbName || 'Course Content',
          count: 5,
          difficulty: 'medium',
          assessment_type: 'quiz',
          auto_create: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Generation failed');
      }
      const data = await res.json();
      // Load the new assessment via /take for safety
      const takeResp = await fetch(`${ASSESSMENT_API}/${data.id}/take`);
      setAssessment(await takeResp.json());
      setAnswers({});
      setResult(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };

  // ── Loading / Error states ──────────────────────────────────────────────────
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
        <button className="btn btn-secondary mt-4" onClick={() => navigate(-1)}>
          ← Go Back
        </button>
      </div>
    );
  }

  // ── Results view ────────────────────────────────────────────────────────────
  if (result) {
    const passed = result.percentage >= 70;
    return (
      <div>
        <div className="page-header">
          <div className="container"><h1>Assessment Results</h1></div>
        </div>
        <div className="container" style={{ maxWidth: 720, paddingTop: 32, paddingBottom: 60 }}>
          {/* Score card */}
          <div className="table-wrap" style={{ padding: 36, textAlign: 'center', marginBottom: 24 }}>
            <div style={{ fontSize: '3.5rem', marginBottom: 12 }}>{passed ? '🎉' : '📖'}</div>
            <h2 style={{ fontSize: '2.8rem', marginBottom: 4, color: passed ? '#166534' : '#92400e' }}>
              {result.percentage.toFixed(0)}%
            </h2>
            <p className="text-muted" style={{ marginBottom: 20 }}>
              {result.correct} of {result.total} correct
            </p>
            <div style={{
              display: 'inline-block', padding: '12px 24px', borderRadius: 12,
              background: passed ? '#dcfce7' : '#fef9c3',
              color: passed ? '#166534' : '#854d0e',
              fontWeight: 600, marginBottom: 24,
            }}>
              {passed
                ? "Great work! You've demonstrated good understanding of this topic."
                : 'Keep studying! Review the material and try again when you\'re ready.'}
            </div>

            {/* Improvement banner */}
            {comparison && <ImprovementBanner comparison={comparison} />}

            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={() => navigate(`/course/${kbId}`)}>
                Back to Course
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setShowFeedback(f => !f)}
              >
                {showFeedback ? 'Hide' : 'Review'} Answers
              </button>
              <button className="btn btn-primary" onClick={() => { setResult(null); setAnswers({}); }}>
                Retake Assessment
              </button>
            </div>
          </div>

          {/* Per-question feedback */}
          {showFeedback && result.feedback_per_question.map((fb, i) => (
            <div key={fb.question_id} className="table-wrap" style={{
              padding: 20, marginBottom: 16,
              borderLeft: `4px solid ${fb.is_correct ? '#22c55e' : '#ef4444'}`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <p style={{ fontWeight: 600, flex: 1, marginRight: 12 }}>
                  <span style={{ color: 'var(--brand)', marginRight: 6 }}>Q{i + 1}.</span>
                  {fb.question_text}
                </p>
                <span style={{
                  flexShrink: 0, fontSize: '0.75rem', fontWeight: 700, padding: '3px 10px',
                  borderRadius: 20, background: fb.is_correct ? '#dcfce7' : '#fee2e2',
                  color: fb.is_correct ? '#166534' : '#991b1b',
                }}>
                  {fb.is_correct ? '✓ Correct' : '✗ Incorrect'}
                </span>
              </div>
              {!fb.is_correct && (
                <div style={{ fontSize: '0.82rem' }}>
                  <p style={{ color: '#991b1b', marginBottom: 4 }}>
                    Your answer: <strong>{fb.submitted_answer ?? 'Not answered'}</strong>
                  </p>
                  <p style={{ color: '#166534' }}>
                    Correct answer: <strong>{fb.correct_answer}</strong>
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Quiz view ───────────────────────────────────────────────────────────────
  const answeredCount = Object.keys(answers).length;
  const totalQ = assessment?.questions.length ?? 0;
  const progressPct = totalQ > 0 ? Math.round((answeredCount / totalQ) * 100) : 0;

  return (
    <div>
      <div className="page-header">
        <div className="container">
          <h1>{assessment?.title ?? 'Assessment'}</h1>
          <p style={{ opacity: 0.85, marginTop: 4 }}>
            {kbName} · {totalQ} questions · {assessment?.assessment_type} assessment
          </p>
        </div>
      </div>

      <div className="container" style={{ maxWidth: 720, paddingTop: 24, paddingBottom: 60 }}>
        {/* Pre/post comparison banner if available */}
        {comparison && <ImprovementBanner comparison={comparison} />}

        {/* Progress bar */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 6 }}>
            <span>Progress</span>
            <span>{answeredCount} / {totalQ} answered</span>
          </div>
          <div style={{ height: 6, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{
              height: '100%', background: 'var(--brand)', borderRadius: 4,
              width: `${progressPct}%`, transition: 'width 0.3s',
            }} />
          </div>
        </div>

        {/* Action bar — AI generate */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20, gap: 10 }}>
          <button
            className="btn btn-secondary"
            style={{ fontSize: '0.82rem', padding: '6px 14px' }}
            onClick={handleGenerateAI}
            disabled={generating}
            title="Generate new questions from your course materials using AI"
          >
            {generating ? '⏳ Generating…' : '✨ AI-Generate Questions'}
          </button>
        </div>

        {/* Questions */}
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
            disabled={submitting || answeredCount < totalQ}
          >
            {submitting ? 'Submitting…' : `Submit (${answeredCount}/${totalQ})`}
          </button>
        </div>
      </div>
    </div>
  );
}
