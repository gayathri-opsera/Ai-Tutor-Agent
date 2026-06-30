import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AdminMonitoringDashboard } from './AdminMonitoringDashboard';

describe('AdminMonitoringDashboard', () => {
  it('renders monitoring metrics', () => {
    render(<AdminMonitoringDashboard />);
    expect(screen.getByLabelText('Admin monitoring dashboard')).toBeInTheDocument();
    expect(screen.getByText(/125,000/)).toBeInTheDocument();
  });
});
