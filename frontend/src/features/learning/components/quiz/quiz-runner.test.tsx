import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { QuizRunner } from './quiz-runner';
import { learningApi } from '@/features/learning/api/learning-api';
import type { QuizForAttempt, QuizResult } from '@/types/learning';

const quiz: QuizForAttempt = {
  id: 'quiz-1',
  lessonId: 'lesson-1',
  title: 'Check: models and encapsulation',
  instructions: 'You need 70% to pass.',
  passingScore: 70,
  timeLimitSeconds: null,
  attemptId: 'attempt-1',
  attemptNumber: 1,
  attemptsRemaining: null,
  questions: [
    {
      id: 'q1',
      prompt: 'Which layer handles logical addressing?',
      questionType: 'single_choice',
      mediaUrl: null,
      points: 1,
      orderIndex: 0,
      matchTargets: [],
      options: [
        { id: 'o1', text: 'Layer 2', orderIndex: 0 },
        { id: 'o2', text: 'Layer 3', orderIndex: 1 },
      ],
    },
    {
      id: 'q2',
      prompt: 'Select every statement that is true of UDP.',
      questionType: 'multiple_choice',
      mediaUrl: null,
      points: 2,
      orderIndex: 1,
      matchTargets: [],
      options: [
        { id: 'o3', text: 'It is connectionless', orderIndex: 0 },
        { id: 'o4', text: 'Its header is 8 bytes', orderIndex: 1 },
        { id: 'o5', text: 'It retransmits lost segments', orderIndex: 2 },
      ],
    },
  ],
};

const passResult: QuizResult = {
  attemptId: 'attempt-1',
  quizId: 'quiz-1',
  lessonId: 'lesson-1',
  status: 'passed',
  passed: true,
  scorePercent: 100,
  pointsEarned: 3,
  pointsPossible: 3,
  passingScore: 70,
  attemptNumber: 1,
  attemptsRemaining: null,
  xpAwarded: 25,
  totalXp: 125,
  level: 2,
  leveledUp: true,
  newAchievements: [],
  results: [
    {
      questionId: 'q1',
      isCorrect: true,
      pointsEarned: 1,
      pointsPossible: 1,
      explanation: 'Layer 3 carries IP addresses.',
      correctOptionIds: ['o2'],
      correctText: null,
      correctOrder: [],
      correctPairs: {},
    },
    {
      questionId: 'q2',
      isCorrect: false,
      pointsEarned: 0,
      pointsPossible: 2,
      explanation: 'UDP does not retransmit.',
      correctOptionIds: ['o3', 'o4'],
      correctText: null,
      correctOrder: [],
      correctPairs: {},
    },
  ],
};

function renderRunner(node: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>);
}

function runner() {
  return (
    <QuizRunner quiz={quiz} courseSlug="network-fundamentals" lessonSlug="osi-model" onRetry={vi.fn()} />
  );
}

describe('QuizRunner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders every question with its point value', () => {
    renderRunner(runner());

    expect(screen.getByText('Which layer handles logical addressing?')).toBeInTheDocument();
    expect(screen.getByText('Select every statement that is true of UDP.')).toBeInTheDocument();
    expect(screen.getByText('1 pt')).toBeInTheDocument();
    expect(screen.getByText('2 pts')).toBeInTheDocument();
  });

  it('shows no correct answers before submission', () => {
    renderRunner(runner());

    expect(screen.queryByText(/Correct answer/)).not.toBeInTheDocument();
    expect(screen.queryByText('Layer 3 carries IP addresses.')).not.toBeInTheDocument();
  });

  it('tracks how many questions are answered', async () => {
    renderRunner(runner());
    expect(screen.getByText('0 of 2 answered')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('radio', { name: 'Layer 3' }));

    expect(screen.getByText('1 of 2 answered')).toBeInTheDocument();
  });

  it('keeps both selections when multi-select options are clicked in quick succession', async () => {
    // The regression this guards: computing the next selection from a prop
    // captured at render time drops one of two rapid clicks.
    renderRunner(runner());

    const first = screen.getByRole('checkbox', { name: 'It is connectionless' });
    const second = screen.getByRole('checkbox', { name: 'Its header is 8 bytes' });
    await userEvent.click(first);
    await userEvent.click(second);

    expect(first).toHaveAttribute('aria-checked', 'true');
    expect(second).toHaveAttribute('aria-checked', 'true');
  });

  it('submits an answer for every question, answered or not', async () => {
    const submit = vi.spyOn(learningApi, 'submitAttempt').mockResolvedValue(passResult);
    renderRunner(runner());

    await userEvent.click(screen.getByRole('radio', { name: 'Layer 3' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit answers' }));

    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    const [attemptId, answers] = submit.mock.calls[0] ?? [];
    expect(attemptId).toBe('attempt-1');
    // Unanswered questions are still submitted so the server grades a full set.
    expect(answers).toHaveLength(2);
  });

  it('shows the score, XP and level-up after grading', async () => {
    vi.spyOn(learningApi, 'submitAttempt').mockResolvedValue(passResult);
    renderRunner(runner());

    await userEvent.click(screen.getByRole('radio', { name: 'Layer 3' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit answers' }));

    expect(await screen.findByText(/Passed — 100%/)).toBeInTheDocument();
    expect(screen.getByText(/\+25 XP/)).toBeInTheDocument();
    expect(screen.getByText(/levelled up to 2/)).toBeInTheDocument();
  });

  it('reveals explanations and correct answers only after grading', async () => {
    vi.spyOn(learningApi, 'submitAttempt').mockResolvedValue(passResult);
    renderRunner(runner());

    await userEvent.click(screen.getByRole('radio', { name: 'Layer 3' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit answers' }));

    expect(await screen.findByText('Layer 3 carries IP addresses.')).toBeInTheDocument();
    expect(screen.getByText('UDP does not retransmit.')).toBeInTheDocument();
    // The wrong answer names what should have been selected.
    expect(screen.getByText(/It is connectionless, Its header is 8 bytes/)).toBeInTheDocument();
  });

  it('locks the inputs once submitted', async () => {
    vi.spyOn(learningApi, 'submitAttempt').mockResolvedValue(passResult);
    renderRunner(runner());

    await userEvent.click(screen.getByRole('radio', { name: 'Layer 3' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit answers' }));

    await screen.findByText(/Passed — 100%/);
    expect(screen.getByRole('radio', { name: 'Layer 2' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
