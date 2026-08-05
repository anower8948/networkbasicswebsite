import '@testing-library/jest-dom/vitest';

/**
 * jsdom implements neither `matchMedia` nor `ResizeObserver`, both of which the
 * theme provider and layout components call on mount. Stubbing them here keeps
 * every test file free of the same boilerplate.
 */
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;
