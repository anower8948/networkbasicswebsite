import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Alert } from './alert';

describe('Alert', () => {
  it('renders its title and body', () => {
    render(
      <Alert title="Confirm your email">Check your inbox for the link.</Alert>,
    );

    expect(screen.getByText('Confirm your email')).toBeInTheDocument();
    expect(screen.getByText('Check your inbox for the link.')).toBeInTheDocument();
  });

  it('announces errors urgently', () => {
    render(<Alert tone="danger">Something failed.</Alert>);
    expect(screen.getByRole('alert')).toHaveTextContent('Something failed.');
  });

  it('announces warnings urgently', () => {
    render(<Alert tone="warning">Careful.</Alert>);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('announces success politely, not as an alert', () => {
    render(<Alert tone="success">Saved.</Alert>);

    expect(screen.getByRole('status')).toHaveTextContent('Saved.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders an action slot', () => {
    render(<Alert action={<button type="button">Resend</button>}>Body</Alert>);
    expect(screen.getByRole('button', { name: 'Resend' })).toBeInTheDocument();
  });
});
