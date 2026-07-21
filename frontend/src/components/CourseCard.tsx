import { useNavigate } from 'react-router-dom';

interface CourseCardProps {
  id: string;
  name: string;
  description?: string;
  docCount?: number;
  progress?: number;          // 0–100
  tag?: string;
  emoji?: string;
  onClick?: () => void;
  enrollButton?: React.ReactNode;  // optional enroll/unenroll button rendered in footer
}

export function CourseCard({
  id, name, description, docCount = 0, progress,
  tag = 'Knowledge Base', emoji = '📚',
  onClick, enrollButton,
}: CourseCardProps) {
  const navigate = useNavigate();
  const handleClick = onClick ?? (() => navigate(`/course/${id}`));

  return (
    <article className="course-card" onClick={handleClick} tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && handleClick()}
      role="button" aria-label={`Open ${name}`}>

      {/* Thumbnail */}
      <div className="course-thumb">
        <span style={{ fontSize: '3rem' }}>{emoji}</span>
        <span className="course-thumb-badge">{tag}</span>
      </div>

      {/* Body */}
      <div className="course-body">
        <h3 className="course-title">{name}</h3>
        {description && (
          <p className="course-instructor" style={{ WebkitLineClamp: 2, display: '-webkit-box', WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {description}
          </p>
        )}

        {/* Tags */}
        <div className="course-meta">
          <span className="course-tag">{docCount} document{docCount !== 1 ? 's' : ''}</span>
          {progress !== undefined && (
            <span className="course-tag">{progress}% complete</span>
          )}
        </div>

        {/* Progress bar */}
        {progress !== undefined && (
          <div className="course-progress">
            <div className="progress-bar-wrap">
              <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
            </div>
            <p className="progress-label">{progress === 100 ? '✅ Completed' : `${progress}% complete`}</p>
          </div>
        )}
      </div>

      <div className="course-footer">
        <span className="course-doc-count">📄 {docCount} doc{docCount !== 1 ? 's' : ''}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {enrollButton}
          <span className="btn btn-ghost btn-sm">Start →</span>
        </div>
      </div>
    </article>
  );
}
