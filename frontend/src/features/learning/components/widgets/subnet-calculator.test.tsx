import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SubnetCalculator } from './subnet-calculator';

/** Set the address field to a known value. */
async function typeAddress(value: string) {
  const field = screen.getByLabelText('IPv4 address');
  await userEvent.clear(field);
  await userEvent.type(field, value);
}

describe('SubnetCalculator', () => {
  it('computes the worked example from the lesson', async () => {
    render(<SubnetCalculator />);
    // Defaults are 192.168.1.100 /26 — the example the subnetting lesson walks
    // through, so a mismatch here means the lesson teaches the wrong answer.
    expect(await screen.findByText('192.168.1.64')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.127')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.65')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.126')).toBeInTheDocument();
    expect(screen.getByText('62')).toBeInTheDocument();
  });

  it('shows the magic number for a non-byte-aligned mask', () => {
    render(<SubnetCalculator />);

    // 256 - 192 = 64 for a /26, in the fourth octet.
    const explanation = screen.getByText(/interesting octet is number/i);
    expect(explanation).toHaveTextContent('octet is number 4');
    expect(explanation).toHaveTextContent('64');
  });

  it('hides the magic number when the mask is byte-aligned', async () => {
    // For a /24 the arithmetic is trivial, so the hint would be noise.
    render(<SubnetCalculator />);
    await userEvent.selectOptions(screen.getByLabelText('Prefix'), '24');

    expect(screen.queryByText(/interesting octet is number/i)).not.toBeInTheDocument();
  });

  it('handles a /24 correctly', async () => {
    render(<SubnetCalculator />);
    await userEvent.selectOptions(screen.getByLabelText('Prefix'), '24');

    expect(screen.getByText('192.168.1.0')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.255')).toBeInTheDocument();
    expect(screen.getByText('254')).toBeInTheDocument();
    expect(screen.getByText('255.255.255.0')).toBeInTheDocument();
  });

  it('handles a /30 point-to-point link', async () => {
    render(<SubnetCalculator />);
    await typeAddress('10.0.0.5');
    await userEvent.selectOptions(screen.getByLabelText('Prefix'), '30');

    expect(screen.getByText('10.0.0.4')).toBeInTheDocument();
    expect(screen.getByText('10.0.0.7')).toBeInTheDocument();
    // 2^2 - 2 = 2 usable addresses, one per router.
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('handles addresses above 127 without sign errors', async () => {
    // JavaScript bitwise ops are signed; 200.x.x.x has the high bit set, so a
    // missing `>>> 0` would produce a negative number and a wrong address.
    render(<SubnetCalculator />);
    await typeAddress('200.100.50.25');
    await userEvent.selectOptions(screen.getByLabelText('Prefix'), '24');

    expect(screen.getByText('200.100.50.0')).toBeInTheDocument();
    expect(screen.getByText('200.100.50.255')).toBeInTheDocument();
  });

  it('computes the wildcard mask', async () => {
    render(<SubnetCalculator />);
    await userEvent.selectOptions(screen.getByLabelText('Prefix'), '24');
    expect(screen.getByText('0.0.0.255')).toBeInTheDocument();
  });

  it('rejects an out-of-range octet', async () => {
    render(<SubnetCalculator />);
    await typeAddress('192.168.1.300');

    expect(screen.getByRole('alert')).toHaveTextContent('valid IPv4 address');
  });

  it('rejects a malformed address', async () => {
    render(<SubnetCalculator />);
    await typeAddress('192.168.1');

    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
