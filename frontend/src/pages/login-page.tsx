import { Link } from 'react-router-dom';

import { AuthLayout } from '@/components/layout/auth-layout';
import { LoginForm } from '@/features/auth/components/login-form';

export default function LoginPage() {
  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to continue building your networking skills."
      footer={
        <>
          New here?{' '}
          <Link
            to="/register"
            className="font-medium text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
          >
            Create an account
          </Link>
        </>
      }
    >
      <LoginForm />
    </AuthLayout>
  );
}
