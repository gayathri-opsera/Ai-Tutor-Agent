import { Navigate } from 'react-router-dom';
import { authService } from './keycloak';

interface Props {
  children: React.ReactNode;
  roles?: string[];
}

export function ProtectedRoute({ children, roles }: Props) {
  const user = authService.getUser();
  if (!user) return <Navigate to="/" replace />;
  if (roles && !roles.some((r) => user.roles.includes(r))) {
    return <div role="alert">Access denied</div>;
  }
  return <>{children}</>;
}
