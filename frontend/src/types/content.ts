/**
 * Lesson content blocks.
 *
 * This union mirrors `backend/app/schemas/content.py` exactly. Because it is a
 * discriminated union on `type`, adding a block server-side without adding a
 * renderer here is a **compile error** in `BlockRenderer`'s exhaustive switch —
 * the two files cannot drift silently.
 */

export interface HeadingBlock {
  type: 'heading';
  level: 2 | 3 | 4;
  text: string;
}

export interface ParagraphBlock {
  type: 'paragraph';
  text: string;
}

export interface ListBlock {
  type: 'list';
  ordered: boolean;
  items: string[];
}

export type CalloutVariant = 'note' | 'tip' | 'warning' | 'important' | 'exam';

export interface CalloutBlock {
  type: 'callout';
  variant: CalloutVariant;
  title: string | null;
  text: string;
}

export type CodeLanguage = 'cisco' | 'bash' | 'python' | 'text' | 'json';

export interface CodeBlock {
  type: 'code';
  language: CodeLanguage;
  code: string;
  caption: string | null;
}

export interface TableBlock {
  type: 'table';
  headers: string[];
  rows: string[][];
  caption: string | null;
}

export interface ImageBlock {
  type: 'image';
  url: string;
  alt: string;
  caption: string | null;
}

export interface DefinitionItem {
  term: string;
  definition: string;
}

export interface DefinitionsBlock {
  type: 'definitions';
  items: DefinitionItem[];
}

export interface DividerBlock {
  type: 'divider';
}

export type InteractiveWidget =
  | 'osi-stack'
  | 'subnet-calculator'
  | 'ipv4-anatomy'
  | 'tcp-handshake';

export interface InteractiveBlock {
  type: 'interactive';
  widget: InteractiveWidget;
  title: string | null;
  config: Record<string, unknown>;
}

export type ContentBlock =
  | HeadingBlock
  | ParagraphBlock
  | ListBlock
  | CalloutBlock
  | CodeBlock
  | TableBlock
  | ImageBlock
  | DefinitionsBlock
  | DividerBlock
  | InteractiveBlock;
