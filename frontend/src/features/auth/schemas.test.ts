import { describe, expect, it } from 'vitest';

import { loginSchema, passwordStrength, registerSchema } from './schemas';

describe('loginSchema', () => {
  it('accepts a well-formed login', () => {
    expect(loginSchema.safeParse({ email: 'a@b.com', password: 'x' }).success).toBe(true);
  });

  it('rejects a malformed email', () => {
    expect(loginSchema.safeParse({ email: 'not-an-email', password: 'x' }).success).toBe(false);
  });
});

describe('registerSchema', () => {
  const valid = {
    fullName: 'Ada Lovelace',
    username: 'ada',
    email: 'ada@example.com',
    password: 'Subnetting2024',
    confirmPassword: 'Subnetting2024',
  };

  it('accepts a complete registration', () => {
    expect(registerSchema.safeParse(valid).success).toBe(true);
  });

  it('rejects mismatched passwords and points at the confirmation field', () => {
    const result = registerSchema.safeParse({ ...valid, confirmPassword: 'Different2024' });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(['confirmPassword']);
    }
  });

  it.each([
    ['too short', 'Short1'],
    ['no digit', 'abcdefghijkl'],
    ['no letter', '123456789012'],
  ])('rejects a password that is %s', (_label, password) => {
    expect(
      registerSchema.safeParse({ ...valid, password, confirmPassword: password }).success,
    ).toBe(false);
  });

  it.each([['ab'], ['has spaces'], ['sym!bols']])('rejects the username %s', (username) => {
    expect(registerSchema.safeParse({ ...valid, username }).success).toBe(false);
  });

  it('treats the full name as optional', () => {
    const { fullName: _fullName, ...withoutName } = valid;
    expect(registerSchema.safeParse(withoutName).success).toBe(true);
  });
});

describe('passwordStrength', () => {
  it('scores an empty password as zero', () => {
    expect(passwordStrength('')).toBe(0);
  });

  it('increases the score as complexity grows', () => {
    expect(passwordStrength('short')).toBeLessThan(passwordStrength('Subnetting2024'));
    expect(passwordStrength('Subnetting2024')).toBeLessThan(
      passwordStrength('Subnetting2024!@#extra'),
    );
  });

  it('never exceeds the maximum of 4', () => {
    expect(passwordStrength('AVeryLongAndComplex1!Password#2024')).toBe(4);
  });
});
