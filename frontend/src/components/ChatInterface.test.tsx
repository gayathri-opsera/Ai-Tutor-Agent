import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatInterface } from './ChatInterface';

describe('ChatInterface', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('renders chat interface with aria labels', () => {
    render(<ChatInterface />);
    expect(screen.getByLabelText('Chat interface')).toBeInTheDocument();
    expect(screen.getByLabelText('Message input')).toBeInTheDocument();
  });

  it('shows new chat button', () => {
    render(<ChatInterface />);
    expect(screen.getByLabelText('New chat session')).toBeInTheDocument();
  });
});
