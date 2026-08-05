import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { XPBar } from './xp-bar';
import type { LevelProgress } from '@/types/api';

const level: LevelProgress = {
  level: 4,
  totalXp: 520,
  currentLevelXp: 519,
  nextLevelXp: 800,
  xpIntoLevel: 1,
  xpForNextLevel: 281,
  percentToNextLevel: 0.4,
  isMaxLevel: false,
};

describe('XPBar', () => {
  it('shows the current level', () => {
    render(<XPBar level={level} />);
    expect(screen.getByText(/Level 4/)).toBeInTheDocument();
  });

  it('exposes progress to assistive technology', () => {
    render(<XPBar level={level} />);

    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });

  it('reports how much XP the next level needs', () => {
    render(<XPBar level={level} />);
    expect(screen.getByText(/280 XP to level 5/)).toBeInTheDocument();
  });

  it('does not advertise a next level at the cap', () => {
    render(
      <XPBar
        level={{
          ...level,
          level: 100,
          isMaxLevel: true,
          percentToNextLevel: 100,
          xpForNextLevel: 0,
        }}
      />,
    );

    expect(screen.getByText('max')).toBeInTheDocument();
    expect(screen.queryByText(/to level 101/)).not.toBeInTheDocument();
  });
});
