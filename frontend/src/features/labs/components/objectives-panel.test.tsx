import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ObjectivesPanel } from './objectives-panel';
import type { CheckResult, LabObjective, ObjectiveResult } from '@/types/lab';

const objectives: LabObjective[] = [
  { id: 'address', title: 'Address both hosts', hint: 'Use the Interfaces tab.', points: 20 },
  { id: 'reach', title: 'PC1 can ping PC2', hint: null, points: 30 },
];

function result(id: string, passed: boolean): ObjectiveResult {
  return {
    objectiveId: id,
    title: id,
    passed,
    pointsEarned: passed ? 20 : 0,
    pointsPossible: 20,
  };
}

function check(objectiveId: string, passed: boolean, detail: string): CheckResult {
  return {
    ruleId: `${objectiveId}-rule`,
    objectiveId,
    passed,
    pointsEarned: passed ? 20 : 0,
    pointsPossible: 20,
    summary: 'PC1 Ethernet0 must be configured with 192.168.10.11',
    detail,
  };
}

function renderPanel(props: Partial<Parameters<typeof ObjectivesPanel>[0]> = {}) {
  const onRequestHint = vi.fn();
  render(
    <ObjectivesPanel
      objectives={objectives}
      results={[]}
      checks={[]}
      hints={{}}
      isRequestingHint={false}
      onRequestHint={onRequestHint}
      {...props}
    />,
  );
  return { onRequestHint };
}

describe('ObjectivesPanel', () => {
  it('lists every objective', () => {
    renderPanel();

    expect(screen.getByText('Address both hosts')).toBeInTheDocument();
    expect(screen.getByText('PC1 can ping PC2')).toBeInTheDocument();
  });

  it('shows an unchecked objective as neither passed nor failed', async () => {
    renderPanel();

    await userEvent.click(screen.getByText('Address both hosts'));

    // Before any check has run, the panel must not imply the learner got it
    // wrong — it says there is nothing to report yet.
    expect(screen.getByText(/Check your work to see/)).toBeInTheDocument();
  });

  it('shows why a check failed', async () => {
    renderPanel({
      results: [result('address', false)],
      checks: [check('address', false, 'It is configured with nothing.')],
    });

    await userEvent.click(screen.getByText('Address both hosts'));

    expect(screen.getByText('It is configured with nothing.')).toBeInTheDocument();
  });

  it('scores each objective out of its own points', () => {
    renderPanel({ results: [result('address', true)] });

    expect(screen.getByText('20/20')).toBeInTheDocument();
  });

  it('offers a hint only where the author wrote one', async () => {
    renderPanel();

    await userEvent.click(screen.getByText('Address both hosts'));
    expect(screen.getByRole('button', { name: /show a hint/i })).toBeInTheDocument();

    await userEvent.click(screen.getByText('PC1 can ping PC2'));
    expect(screen.queryByRole('button', { name: /show a hint/i })).not.toBeInTheDocument();
  });

  it('requests a hint for the objective it was asked from', async () => {
    const { onRequestHint } = renderPanel();

    await userEvent.click(screen.getByText('Address both hosts'));
    await userEvent.click(screen.getByRole('button', { name: /show a hint/i }));

    expect(onRequestHint).toHaveBeenCalledWith('address');
  });

  it('shows a revealed hint in place of the button', async () => {
    renderPanel({ hints: { address: 'Use the Interfaces tab.' } });

    await userEvent.click(screen.getByText('Address both hosts'));

    expect(screen.getByText('Use the Interfaces tab.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show a hint/i })).not.toBeInTheDocument();
  });

  it('shows one objective at a time', async () => {
    renderPanel({
      checks: [check('address', false, 'It is configured with nothing.')],
    });

    await userEvent.click(screen.getByText('Address both hosts'));
    expect(screen.getByText('It is configured with nothing.')).toBeInTheDocument();

    await userEvent.click(screen.getByText('PC1 can ping PC2'));
    expect(screen.queryByText('It is configured with nothing.')).not.toBeInTheDocument();
  });
});
