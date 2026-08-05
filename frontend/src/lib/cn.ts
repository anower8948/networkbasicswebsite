import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge class names, resolving Tailwind conflicts in favour of the last value.
 *
 * `clsx` handles conditionals; `twMerge` ensures a caller-supplied `px-6` beats
 * a component's default `px-4` instead of both landing in the class list where
 * the winner would depend on stylesheet order.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
