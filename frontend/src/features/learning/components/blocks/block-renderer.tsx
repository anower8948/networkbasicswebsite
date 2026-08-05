/**
 * Renders one content block.
 *
 * The switch is **exhaustive**: `assertNever` in the default branch makes
 * adding a block type to `types/content.ts` without adding a case here a
 * compile error, so the renderer can never silently drop content.
 */

import {
  CalloutBlockView,
  CodeBlockView,
  DefinitionsBlockView,
  HeadingBlockView,
  ImageBlockView,
  ListBlockView,
  ParagraphBlockView,
  TableBlockView,
} from './primitives';
import { InteractiveBlockView } from './interactive-block';
import type { ContentBlock } from '@/types/content';

/** Fails at compile time if a union member is unhandled. */
function assertNever(value: never): never {
  throw new Error(`Unhandled content block: ${JSON.stringify(value)}`);
}

export function BlockRenderer({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case 'heading':
      return <HeadingBlockView block={block} />;
    case 'paragraph':
      return <ParagraphBlockView block={block} />;
    case 'list':
      return <ListBlockView block={block} />;
    case 'callout':
      return <CalloutBlockView block={block} />;
    case 'code':
      return <CodeBlockView block={block} />;
    case 'table':
      return <TableBlockView block={block} />;
    case 'image':
      return <ImageBlockView block={block} />;
    case 'definitions':
      return <DefinitionsBlockView block={block} />;
    case 'divider':
      return <hr className="my-8 border-t border-[var(--hairline)]" />;
    case 'interactive':
      return <InteractiveBlockView block={block} />;
    default:
      return assertNever(block);
  }
}
