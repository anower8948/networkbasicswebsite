import { cn } from '@/lib/cn';

const SIZES = {
  sm: 'size-8 text-[12px]',
  md: 'size-10 text-sm',
  lg: 'size-16 text-xl',
  xl: 'size-24 text-3xl',
} as const;

interface AvatarProps {
  name: string;
  /** `undefined` is spelled out because `exactOptionalPropertyTypes` is on and
   *  callers pass a possibly-absent field straight through. */
  imageUrl?: string | null | undefined;
  size?: keyof typeof SIZES;
  className?: string;
}

/** First letters of the first and last words — "Ada Lovelace" → "AL". */
function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  const first = words[0]?.[0] ?? '';
  const last = words.length > 1 ? (words[words.length - 1]?.[0] ?? '') : '';
  return (first + last).toUpperCase();
}

/**
 * Profile image, falling back to initials on a hue derived from the name.
 *
 * Deriving the hue from the name means a given user keeps the same colour
 * everywhere without storing one, which makes them recognisable in lists.
 */
export function Avatar({ name, imageUrl, size = 'md', className }: AvatarProps) {
  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt={name}
        className={cn('rounded-full object-cover', SIZES[size], className)}
      />
    );
  }

  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) % 360;
  }

  return (
    <span
      aria-hidden
      title={name}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white',
        SIZES[size],
        className,
      )}
      style={{
        background: `linear-gradient(135deg, oklch(0.68 0.16 ${hash}), oklch(0.55 0.19 ${(hash + 40) % 360}))`,
      }}
    >
      {initialsFrom(name)}
    </span>
  );
}
