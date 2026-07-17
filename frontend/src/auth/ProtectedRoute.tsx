import { Navigate } from 'react-router-dom';
import { useUser } from './UserContext';

interface Props {
  children: React.ReactNode;
  roles?: string[];
}

export function ProtectedRoute({ children, roles }: Props) {
  const { user, initializing } = useUser();

  if (initializing) return null;
  if (!user) return <Navigate to="/" replace />;
  if (roles && !roles.some(r => user.roles.includes(r))) {
    return <div role="alert">Access denied</div>;
  }
  return <>{children}</>;
}
