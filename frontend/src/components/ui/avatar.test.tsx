import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Avatar } from './avatar';

describe('Avatar', () => {
  it('renders the image when one is supplied', () => {
    render(<Avatar name="Ada Lovelace" imageUrl="https://example.com/ada.jpg" />);

    const image = screen.getByRole('img', { name: 'Ada Lovelace' });
    expect(image).toHaveAttribute('src', 'https://example.com/ada.jpg');
  });

  it('falls back to first and last initials', () => {
    render(<Avatar name="Ada Lovelace" />);
    expect(screen.getByTitle('Ada Lovelace')).toHaveTextContent('AL');
  });

  it('uses a single initial for a one-word name', () => {
    render(<Avatar name="ada" />);
    expect(screen.getByTitle('ada')).toHaveTextContent('A');
  });

  it('ignores middle names', () => {
    render(<Avatar name="Ada King Lovelace" />);
    expect(screen.getByTitle('Ada King Lovelace')).toHaveTextContent('AL');
  });

  it('does not crash on an empty name', () => {
    render(<Avatar name="" />);
    expect(screen.getByTitle('')).toHaveTextContent('?');
  });

  it('gives the same name the same colour every time', () => {
    const { container: first } = render(<Avatar name="Ada Lovelace" />);
    const { container: second } = render(<Avatar name="Ada Lovelace" />);

    const styleOf = (root: HTMLElement) => root.querySelector('span')?.getAttribute('style');
    expect(styleOf(first)).toBe(styleOf(second));
  });
});
