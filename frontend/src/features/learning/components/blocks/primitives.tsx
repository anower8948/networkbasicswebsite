/** Presentational renderers for the non-interactive content blocks. */

import { BookMarked, Info, Lightbulb, TriangleAlert, Zap } from 'lucide-react';

import { GlassPanel } from '@/components/ui/glass-panel';
import { cn } from '@/lib/cn';
import type {
  CalloutBlock,
  CalloutVariant,
  CodeBlock,
  DefinitionsBlock,
  HeadingBlock,
  ImageBlock,
  ListBlock,
  ParagraphBlock,
  TableBlock,
} from '@/types/content';

export function HeadingBlockView({ block }: { block: HeadingBlock }) {
  const className = cn(
    'text-title scroll-mt-24 font-semibold',
    block.level === 2 && 'mt-10 text-[21px] first:mt-0',
    block.level === 3 && 'mt-8 text-[17px]',
    block.level === 4 && 'mt-6 text-[15px]',
  );

  // Rendered as the real heading level so the document outline is correct for
  // screen readers and in-page navigation.
  if (block.level === 2) return <h2 className={className}>{block.text}</h2>;
  if (block.level === 3) return <h3 className={className}>{block.text}</h3>;
  return <h4 className={className}>{block.text}</h4>;
}

export function ParagraphBlockView({ block }: { block: ParagraphBlock }) {
  return (
    <p className="mt-4 text-[15px] leading-[1.75] text-[var(--text-secondary)]">{block.text}</p>
  );
}

export function ListBlockView({ block }: { block: ListBlock }) {
  const items = block.items.map((item, index) => (
    <li key={index} className="pl-1.5 leading-[1.7]">
      {item}
    </li>
  ));

  const className =
    'mt-4 flex flex-col gap-2 pl-6 text-[15px] text-[var(--text-secondary)] marker:text-[var(--text-tertiary)]';

  return block.ordered ? (
    <ol className={cn(className, 'list-decimal')}>{items}</ol>
  ) : (
    <ul className={cn(className, 'list-disc')}>{items}</ul>
  );
}

const CALLOUT_STYLES: Record<
  CalloutVariant,
  { color: string; Icon: typeof Info; label: string }
> = {
  note: { color: 'var(--color-info)', Icon: Info, label: 'Note' },
  tip: { color: 'var(--color-success)', Icon: Lightbulb, label: 'Tip' },
  warning: { color: 'var(--color-warning)', Icon: TriangleAlert, label: 'Warning' },
  important: { color: 'var(--color-danger)', Icon: Zap, label: 'Important' },
  // Exam notes get their own treatment — learners scan for these.
  exam: { color: 'var(--color-track-advanced)', Icon: BookMarked, label: 'Exam tip' },
};

export function CalloutBlockView({ block }: { block: CalloutBlock }) {
  const { color, Icon, label } = CALLOUT_STYLES[block.variant];

  return (
    <aside
      className="mt-6 flex gap-3.5 rounded-[var(--radius-md)] border p-4"
      style={{
        borderColor: `color-mix(in oklab, ${color} 28%, transparent)`,
        backgroundColor: `color-mix(in oklab, ${color} 8%, transparent)`,
      }}
    >
      <Icon className="mt-0.5 size-[18px] shrink-0" style={{ color }} aria-hidden />
      <div className="min-w-0">
        <p className="text-[13px] font-semibold" style={{ color }}>
          {block.title ?? label}
        </p>
        <p className="mt-1.5 text-[14px] leading-[1.65] text-[var(--text-secondary)]">
          {block.text}
        </p>
      </div>
    </aside>
  );
}

/**
 * Highlights an IOS transcript.
 *
 * Deliberately a small regex pass rather than a syntax-highlighting library:
 * the grammar here is "prompt, command, argument", and shipping a 200 kB
 * highlighter to bold a few keywords is a bad trade on a lesson page.
 */
function highlightCisco(code: string) {
  return code.split('\n').map((line, index) => {
    const promptMatch = /^([\w.-]+(?:\([\w-]+\))?[>#])(\s*)(.*)$/.exec(line);

    if (promptMatch) {
      const [, prompt, space, command] = promptMatch;
      return (
        <div key={index}>
          <span className="text-[var(--color-track-intermediate)]">{prompt}</span>
          {space}
          <span className="text-[var(--text-primary)]">{command}</span>
        </div>
      );
    }
    return (
      <div key={index} className="text-[var(--text-secondary)]">
        {line || ' '}
      </div>
    );
  });
}

export function CodeBlockView({ block }: { block: CodeBlock }) {
  return (
    <figure className="mt-6">
      <GlassPanel material="thin" radius="md" className="overflow-hidden">
        <div className="hairline-b flex items-center justify-between px-4 py-2">
          <span className="text-[11px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
            {block.language === 'cisco' ? 'Cisco IOS' : block.language}
          </span>
        </div>
        {/* Wide transcripts scroll inside the block, never the page. */}
        <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-[1.7]">
          <code>{block.language === 'cisco' ? highlightCisco(block.code) : block.code}</code>
        </pre>
      </GlassPanel>
      {block.caption && (
        <figcaption className="mt-2 text-[13px] text-[var(--text-tertiary)]">
          {block.caption}
        </figcaption>
      )}
    </figure>
  );
}

export function TableBlockView({ block }: { block: TableBlock }) {
  return (
    <figure className="mt-6">
      <GlassPanel radius="md" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[14px]">
            <thead>
              <tr className="hairline-b">
                {block.headers.map((header) => (
                  <th
                    key={header}
                    scope="col"
                    className="px-4 py-2.5 text-left text-[13px] font-semibold whitespace-nowrap"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  className="border-t border-[var(--hairline)] text-[var(--text-secondary)]"
                >
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-4 py-2.5 align-top">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassPanel>
      {block.caption && (
        <figcaption className="mt-2 text-[13px] text-[var(--text-tertiary)]">
          {block.caption}
        </figcaption>
      )}
    </figure>
  );
}

export function ImageBlockView({ block }: { block: ImageBlock }) {
  return (
    <figure className="mt-6">
      <img
        src={block.url}
        alt={block.alt}
        loading="lazy"
        className="w-full rounded-[var(--radius-md)] border border-[var(--hairline)]"
      />
      {block.caption && (
        <figcaption className="mt-2 text-[13px] text-[var(--text-tertiary)]">
          {block.caption}
        </figcaption>
      )}
    </figure>
  );
}

export function DefinitionsBlockView({ block }: { block: DefinitionsBlock }) {
  return (
    <dl className="mt-6 flex flex-col gap-3">
      {block.items.map((item) => (
        <div
          key={item.term}
          className="rounded-[var(--radius-sm)] border border-[var(--hairline)] p-3.5"
        >
          <dt className="text-[14px] font-semibold">{item.term}</dt>
          <dd className="mt-1 text-[14px] leading-[1.65] text-[var(--text-secondary)]">
            {item.definition}
          </dd>
        </div>
      ))}
    </dl>
  );
}
