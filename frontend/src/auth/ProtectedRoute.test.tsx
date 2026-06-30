import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { BrowserRouter } from 'react-router-dom';
import { ProtectedRoute } from '../ProtectedRoute';

describe('ProtectedRoute', () => {
  it('renders children when authenticated', () => {
    render(
      <BrowserRouter>
        <ProtectedRoute><div>Protected content</div></ProtectedRoute>
      </BrowserRouter>,
    );
    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });
});
