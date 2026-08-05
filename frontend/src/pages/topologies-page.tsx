import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Network, Plus, Trash2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { topologyApi } from '@/features/topology/api/topology-api';
import { topologyKeys } from '@/lib/query-client';

export default function TopologiesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: topologyKeys.list,
    queryFn: () => topologyApi.list(),
  });

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: topologyKeys.list });

  const remove = useMutation({
    mutationFn: (id: string) => topologyApi.remove(id),
    onSuccess: invalidate,
  });

  const duplicate = useMutation({
    mutationFn: (id: string) => topologyApi.duplicate(id),
    onSuccess: invalidate,
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-display text-[28px] leading-tight font-semibold">Simulator</h1>
          <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
            Design networks, cable them up, and save your work.
          </p>
        </div>
        <Button
          size="lg"
          leadingIcon={<Plus className="size-4" />}
          onClick={() => void navigate('/simulator/new')}
        >
          New topology
        </Button>
      </header>

      {error && <Alert tone="danger">Could not load your topologies.</Alert>}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner size="lg" className="text-accent-500" label="Loading topologies" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <GlassPanel radius="xl" className="flex flex-col items-center gap-4 p-12 text-center">
          <span className="flex size-14 items-center justify-center rounded-[var(--radius-lg)] bg-accent-500/12">
            <Network className="size-7 text-accent-500" aria-hidden />
          </span>
          <div>
            <p className="text-[15px] font-medium">No topologies yet</p>
            <p className="mt-1 max-w-sm text-[13px] text-[var(--text-secondary)]">
              Start with a couple of PCs and a switch, then cable them together and watch the
              designer check your work.
            </p>
          </div>
          <Button leadingIcon={<Plus className="size-4" />} onClick={() => void navigate('/simulator/new')}>
            Create your first topology
          </Button>
        </GlassPanel>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.items.map((topology) => (
            <GlassPanel key={topology.id} radius="xl" className="flex flex-col gap-3 p-5">
              <Link to={`/simulator/${topology.id}`} className="flex-1">
                <h2 className="text-title text-[15px] font-semibold">{topology.name}</h2>
                {topology.description && (
                  <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
                    {topology.description}
                  </p>
                )}
                <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">
                  {topology.deviceCount} device{topology.deviceCount === 1 ? '' : 's'} · updated{' '}
                  {new Date(topology.updatedAt).toLocaleDateString()}
                </p>
              </Link>

              <div className="hairline-t flex items-center gap-1 pt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => duplicate.mutate(topology.id)}
                  aria-label={`Duplicate ${topology.name}`}
                >
                  <Copy className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    // Deleting a design is irreversible, so confirm first.
                    if (window.confirm(`Delete "${topology.name}"? This cannot be undone.`)) {
                      remove.mutate(topology.id);
                    }
                  }}
                  aria-label={`Delete ${topology.name}`}
                >
                  <Trash2 className="size-3.5" />
                </Button>
                <Link
                  to={`/simulator/${topology.id}`}
                  className="ml-auto text-[13px] text-accent-600 transition-opacity hover:opacity-80 dark:text-accent-400"
                >
                  Open
                </Link>
              </div>
            </GlassPanel>
          ))}
        </div>
      )}
    </div>
  );
}
