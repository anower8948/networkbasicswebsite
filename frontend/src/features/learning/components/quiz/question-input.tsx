/**
 * Renders the input control for one question, dispatched on question type.
 *
 * Every branch is a controlled component reporting a complete `QuizAnswer`, so
 * the runner never has to know how a given type stores its response.
 */

import { GripVertical } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';
import type { QuizAnswer, QuizQuestionForAttempt } from '@/types/learning';

/**
 * An answer, or an updater applied to the previous one.
 *
 * Multi-select needs the updater form. Computing the next selection from the
 * `answer` prop is only correct if a re-render happens between clicks — two
 * clicks in the same tick would both read the same stale value and the first
 * selection would be silently dropped.
 */
export type AnswerUpdate = QuizAnswer | ((previous: QuizAnswer | undefined) => QuizAnswer);

interface QuestionInputProps {
  question: QuizQuestionForAttempt;
  answer: QuizAnswer | undefined;
  disabled: boolean;
  onChange: (update: AnswerUpdate) => void;
}

function ChoiceInput({ question, answer, disabled, onChange }: QuestionInputProps) {
  const isMulti = question.questionType === 'multiple_choice';
  const selected = new Set(answer?.optionIds ?? []);

  const toggle = (optionId: string) => {
    if (!isMulti) {
      onChange({ questionId: question.id, optionIds: [optionId] });
      return;
    }
    // Functional form: the toggle is applied to whatever the parent currently
    // holds, not to a prop captured at render time.
    onChange((previous) => {
      const next = new Set(previous?.optionIds ?? []);
      if (next.has(optionId)) next.delete(optionId);
      else next.add(optionId);
      return { questionId: question.id, optionIds: [...next] };
    });
  };

  return (
    // A radiogroup for single-answer, a plain group for multi — the roles must
    // match the behaviour or keyboard users get the wrong interaction model.
    <div
      role={isMulti ? 'group' : 'radiogroup'}
      aria-label={question.prompt}
      className="flex flex-col gap-2"
    >
      {question.options.map((option) => {
        const isSelected = selected.has(option.id);
        return (
          <button
            key={option.id}
            type="button"
            role={isMulti ? 'checkbox' : 'radio'}
            aria-checked={isSelected}
            disabled={disabled}
            onClick={() => toggle(option.id)}
            className={cn(
              'flex items-center gap-3 rounded-[var(--radius-sm)] border px-3.5 py-2.5 text-left',
              'transition-all duration-[var(--duration-fast)]',
              'disabled:cursor-default disabled:opacity-70',
              isSelected
                ? 'border-accent-500 bg-accent-500/10'
                : 'border-[var(--hairline)] hover:border-[var(--text-tertiary)]',
            )}
          >
            <span
              aria-hidden
              className={cn(
                'flex size-4 shrink-0 items-center justify-center border',
                isMulti ? 'rounded-[4px]' : 'rounded-full',
                isSelected ? 'border-accent-500 bg-accent-500' : 'border-[var(--text-tertiary)]',
              )}
            >
              {isSelected && (
                <span
                  className={cn('bg-white', isMulti ? 'size-1.5 rounded-[1px]' : 'size-1.5 rounded-full')}
                />
              )}
            </span>
            <span className="text-[14px]">{option.text}</span>
          </button>
        );
      })}
    </div>
  );
}

function OrderingInput({ question, answer, disabled, onChange }: QuestionInputProps) {
  // The order lives in `values` as option *text*, which is what the server
  // compares against. Initialised from the shuffled delivery order.
  const current = answer?.values ?? question.options.map((option) => option.text);

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= current.length) return;

    const next = [...current];
    const moved = next[index];
    const displaced = next[target];
    if (moved === undefined || displaced === undefined) return;
    next[index] = displaced;
    next[target] = moved;
    onChange({ questionId: question.id, values: next });
  };

  return (
    <ol className="flex flex-col gap-2">
      {current.map((value, index) => (
        <li
          key={value}
          className="flex items-center gap-3 rounded-[var(--radius-sm)] border border-[var(--hairline)] px-3 py-2.5"
        >
          <GripVertical className="size-4 shrink-0 text-[var(--text-tertiary)]" aria-hidden />
          <span className="flex-1 text-[14px]">{value}</span>
          {/* Buttons rather than drag-and-drop: reordering must be reachable
              by keyboard and on touch without a drag library. */}
          <span className="flex gap-1">
            <button
              type="button"
              disabled={disabled || index === 0}
              onClick={() => move(index, -1)}
              aria-label={`Move ${value} up`}
              className="rounded-[var(--radius-xs)] px-2 py-1 text-[12px] text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)] disabled:opacity-30"
            >
              ↑
            </button>
            <button
              type="button"
              disabled={disabled || index === current.length - 1}
              onClick={() => move(index, 1)}
              aria-label={`Move ${value} down`}
              className="rounded-[var(--radius-xs)] px-2 py-1 text-[12px] text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)] disabled:opacity-30"
            >
              ↓
            </button>
          </span>
        </li>
      ))}
    </ol>
  );
}

function MatchingInput({ question, answer, disabled, onChange }: QuestionInputProps) {
  const pairs = answer?.pairs ?? {};

  return (
    <div className="flex flex-col gap-2">
      {question.options.map((option) => (
        <div key={option.id} className="flex flex-col gap-1.5 sm:flex-row sm:items-center">
          <span className="flex-1 text-[14px]">{option.text}</span>
          <select
            value={pairs[option.id] ?? ''}
            disabled={disabled}
            onChange={(event) =>
              onChange({
                questionId: question.id,
                pairs: { ...pairs, [option.id]: event.target.value },
              })
            }
            aria-label={`Match for ${option.text}`}
            className="glass-inset h-10 rounded-[var(--radius-sm)] px-3 text-[14px] focus:border-accent-500 focus:outline-none sm:w-56"
          >
            <option value="">Choose…</option>
            {question.matchTargets.map((target) => (
              <option key={target} value={target}>
                {target}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}

function TextInput({ question, answer, disabled, onChange }: QuestionInputProps) {
  const isCli = question.questionType === 'cli_command';

  return (
    <Input
      value={answer?.text ?? ''}
      disabled={disabled}
      spellCheck={false}
      autoComplete="off"
      placeholder={
        isCli
          ? 'Type the command exactly as you would in the CLI'
          : question.questionType === 'subnet_calc'
            ? 'e.g. 192.168.1.0'
            : 'Your answer'
      }
      className={isCli || question.questionType === 'subnet_calc' ? 'font-mono' : undefined}
      onChange={(event) => onChange({ questionId: question.id, text: event.target.value })}
    />
  );
}

export function QuestionInput(props: QuestionInputProps) {
  switch (props.question.questionType) {
    case 'single_choice':
    case 'multiple_choice':
    case 'true_false':
      return <ChoiceInput {...props} />;
    case 'ordering':
      return <OrderingInput {...props} />;
    case 'matching':
      return <MatchingInput {...props} />;
    case 'fill_blank':
    case 'subnet_calc':
    case 'cli_command':
      return <TextInput {...props} />;
    default:
      return null;
  }
}
