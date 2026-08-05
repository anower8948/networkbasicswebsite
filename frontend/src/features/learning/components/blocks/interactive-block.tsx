/**
 * Dispatches an `interactive` block to its widget.
 *
 * Like the block renderer, the switch is exhaustive: adding a widget to the
 * backend's `Literal` and to `InteractiveWidget` without registering it here
 * is a compile error.
 */

import { IPv4Anatomy } from '../widgets/ipv4-anatomy';
import { OSIStack } from '../widgets/osi-stack';
import { SubnetCalculator } from '../widgets/subnet-calculator';
import { TCPHandshake } from '../widgets/tcp-handshake';
import type { InteractiveBlock } from '@/types/content';

function assertNever(value: never): never {
  throw new Error(`Unhandled interactive widget: ${JSON.stringify(value)}`);
}

function widgetFor(widget: InteractiveBlock['widget']) {
  switch (widget) {
    case 'osi-stack':
      return <OSIStack />;
    case 'subnet-calculator':
      return <SubnetCalculator />;
    case 'ipv4-anatomy':
      return <IPv4Anatomy />;
    case 'tcp-handshake':
      return <TCPHandshake />;
    default:
      return assertNever(widget);
  }
}

export function InteractiveBlockView({ block }: { block: InteractiveBlock }) {
  return (
    <section className="mt-6">
      {block.title && (
        <p className="mb-2.5 text-[12px] font-medium tracking-wide text-[var(--text-tertiary)] uppercase">
          {block.title}
        </p>
      )}
      {widgetFor(block.widget)}
    </section>
  );
}
