import { useNavigate } from 'react-router-dom';

interface CourseCardProps {
  id: string;
  name: string;
  description?: string;
  docCount?: number;
  progress?: number;          // 0–100
  tag?: string;
  emoji?: string;
  rating?: number;            // 0–5
  ratingCount?: number;
  onClick?: () => void;
}

function Stars({ rating }: { rating: number }) {
  return (
    <div className="stars" aria-label={`Rating: ${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={`star${i <= Math.round(rating) ? '' : ' empty'}`}>★</span>
      ))}
    </div>
  );
}

export function CourseCard({
  id, name, description, docCount = 0, progress,
  tag = 'Knowledge Base', emoji = '📚',
  rating = 4.5, ratingCount = 0,
  onClick,
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

        {/* Rating */}
        <div className="course-rating">
          <span className="course-rating-score">{rating.toFixed(1)}</span>
          <Stars rating={rating} />
          {ratingCount > 0 && (
            <span className="course-rating-count">({ratingCount.toLocaleString()})</span>
          )}
        </div>

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
        <span className="btn btn-ghost btn-sm">Start →</span>
      </div>
    </article>
  );
}
