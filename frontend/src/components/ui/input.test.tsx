import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Input } from './input';

describe('Input', () => {
  it('associates the label with the control', () => {
    render(<Input label="Email" />);
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('announces errors and marks the field invalid', () => {
    render(<Input label="Email" error="Enter a valid email address." />);

    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a valid email address.');
    // The error must be referenced, or a screen reader never reads it.
    expect(input.getAttribute('aria-describedby')).toBeTruthy();
  });

  it('shows the hint when there is no error', () => {
    render(<Input label="Username" hint="Letters and numbers only." />);
    expect(screen.getByText('Letters and numbers only.')).toBeInTheDocument();
  });

  it('hides the hint once an error appears', () => {
    render(<Input label="Username" hint="Letters and numbers only." error="Already taken." />);

    expect(screen.queryByText('Letters and numbers only.')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Already taken.');
  });
});
