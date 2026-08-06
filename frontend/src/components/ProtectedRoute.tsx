import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { Spinner } from '@/components/ui/States';
import { useAuth } from '@/hooks/useAuth';

/**
 * Gate for authenticated routes.
 *
 * Renders nothing decisive until the session has been rehydrated, otherwise a
 * page refresh would bounce an authenticated user to the login screen before
 * the token check completes.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-sunken">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  if (!isAuthenticated) {
    // `state.from` lets the login screen return the user where they intended.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
