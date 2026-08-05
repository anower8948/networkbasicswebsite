/**
 * Client-side form schemas.
 *
 * These mirror the server's rules so the user gets immediate feedback, but they
 * are a convenience, not a control: the backend re-validates everything. Where
 * the two could drift (password policy), the server remains authoritative and
 * its field errors are merged into the form.
 */

import { z } from 'zod';

const PASSWORD_MIN_LENGTH = 10;

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters.`)
  .max(128, 'Use at most 128 characters.')
  .regex(/[A-Za-z]/, 'Include at least one letter.')
  .regex(/\d/, 'Include at least one digit.');

export const loginSchema = z.object({
  email: z.string().min(1, 'Enter your email address.').email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
});

export const registerSchema = z
  .object({
    fullName: z.string().max(120, 'Use at most 120 characters.').optional(),
    username: z
      .string()
      .min(3, 'Use at least 3 characters.')
      .max(32, 'Use at most 32 characters.')
      .regex(
        /^[a-zA-Z0-9_-]+$/,
        'Use only letters, numbers, hyphens and underscores.',
      ),
    email: z.string().min(1, 'Enter your email address.').email('Enter a valid email address.'),
    password: passwordSchema,
    confirmPassword: z.string().min(1, 'Confirm your password.'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: 'Passwords do not match.',
    path: ['confirmPassword'],
  });

export type LoginFormValues = z.infer<typeof loginSchema>;
export type RegisterFormValues = z.infer<typeof registerSchema>;

/** Rough strength estimate (0–4) for the registration meter. */
export function passwordStrength(password: string): number {
  if (!password) return 0;
  let score = 0;
  if (password.length >= PASSWORD_MIN_LENGTH) score += 1;
  if (password.length >= 14) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}
