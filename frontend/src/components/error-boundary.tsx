import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-phase errors so one broken component does not blank the page.
 *
 * Still a class component: React provides no hook equivalent of
 * `componentDidCatch`, and this is the one place a class is required.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Part 10 forwards this to Azure Application Insights.
    console.error('Unhandled render error:', error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    return (
      <div className="flex min-h-dvh items-center justify-center px-5">
        <div className="glass-strong max-w-md rounded-[var(--radius-2xl)] p-10 text-center">
          <h1 className="text-title text-xl font-semibold">Something went wrong</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            The page failed to render. Reloading usually clears it.
          </p>
          {import.meta.env.DEV && (
            <pre className="mt-4 max-h-40 overflow-auto rounded-[var(--radius-sm)] bg-[var(--surface-sunken)] p-3 text-left text-[12px] whitespace-pre-wrap text-[var(--color-danger)]">
              {error.message}
            </pre>
          )}
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-6 inline-flex h-11 items-center justify-center rounded-[var(--radius-sm)] bg-accent-500 px-5 text-sm font-medium text-white transition-colors hover:bg-accent-600"
          >
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}
