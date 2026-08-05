import { useContext } from 'react';

import { ThemeContext } from '@/providers/theme-provider';

/** Access theme state. Throws if used outside `ThemeProvider`. */
export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error('useTheme must be used within a ThemeProvider.');
  }
  return context;
}
