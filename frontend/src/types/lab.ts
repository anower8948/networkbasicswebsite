/**
 * Lab types, mirroring `app/schemas/lab.py`.
 *
 * Only the **learner-facing** projections are modelled here. Grading rules and
 * fault injections have no TypeScript counterpart on purpose: they never reach
 * the browser, and giving them a type would invite someone to fetch them.
 */

import type { TopologyDocument } from './topology';

export type LabKind = 'guided' | 'challenge' | 'troubleshooting' | 'design';

export type Difficulty = 'beginner' | 'intermediate' | 'advanced' | 'expert';

export type AttemptStatus =
  | 'in_progress'
  | 'submitted'
  | 'passed'
  | 'failed'
  | 'abandoned';

export const LAB_KIND_LABELS: Record<LabKind, string> = {
  guided: 'Guided',
  challenge: 'Challenge',
  troubleshooting: 'Troubleshooting',
  design: 'Design',
};

/** What each kind asks of the learner — shown on the card and the briefing. */
export const LAB_KIND_BLURBS: Record<LabKind, string> = {
  guided: 'Step-by-step, with hints on every objective.',
  challenge: 'A goal and a blank slate. Work out the how.',
  troubleshooting: 'Something is broken. Find it and fix it.',
  design: 'Meet a set of requirements, your way.',
};

export interface LabSummary {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  kind: LabKind;
  scenarioType: string | null;
  difficulty: Difficulty;
  estimatedMinutes: number;
  passingScore: number;
  xpReward: number;
  objectiveCount: number;
  bestScore: number | null;
  status: AttemptStatus | null;
}

export interface LabObjective {
  id: string;
  title: string;
  hint: string | null;
  points: number;
}

export interface LabDetail extends LabSummary {
  requirements: string[];
  objectives: LabObjective[];
  timeLimitSeconds: number | null;
}

export interface CheckResult {
  ruleId: string;
  objectiveId: string | null;
  passed: boolean;
  pointsEarned: number;
  pointsPossible: number;
  summary: string;
  detail: string | null;
}

export interface ObjectiveResult {
  objectiveId: string;
  title: string;
  passed: boolean;
  pointsEarned: number;
  pointsPossible: number;
}

export interface LabAttempt {
  id: string;
  labId: string;
  attemptNumber: number;
  status: AttemptStatus;
  workingTopology: TopologyDocument;
  checkResults: CheckResult[];
  scorePercent: number | null;
  hintsUsed: number;
  timeSpentSeconds: number;
  startedAt: string | null;
  submittedAt: string | null;
}

export interface LabGradeResult {
  attemptId: string;
  labId: string;
  status: AttemptStatus;
  passed: boolean;
  scorePercent: number;
  pointsEarned: number;
  pointsPossible: number;
  passingScore: number;
  results: CheckResult[];
  objectives: ObjectiveResult[];
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
  faultExplanations: string[];
}

export interface HintResponse {
  objectiveId: string;
  hint: string | null;
  hintsUsed: number;
}
