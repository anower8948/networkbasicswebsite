import { Link } from 'react-router-dom';

import { AuthLayout } from '@/components/layout/auth-layout';
import { RegisterForm } from '@/features/auth/components/register-form';

export default function RegisterPage() {
  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start with the fundamentals and work up to CCNA and beyond."
      footer={
        <>
          Already have an account?{' '}
          <Link
            to="/login"
            className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
          >
            Sign in
          </Link>
        </>
      }
    >
      <RegisterForm />
    </AuthLayout>
  );
}
