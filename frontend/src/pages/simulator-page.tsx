/**
 * The network designer.
 *
 * Layout: device palette on the left, canvas in the middle, inspector on the
 * right. Save is explicit, with an unsaved-changes indicator — autosaving a
 * design a learner is experimenting with would overwrite work they may want to
 * abandon.
 */

import { ReactFlowProvider } from '@xyflow/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  Download,
  Redo2,
  Save,
  TriangleAlert,
  Undo2,
  Upload,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import '@xyflow/react/dist/style.css';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { TopologyWorkspace } from '@/features/topology/components/topology-workspace';
import { topologyApi } from '@/features/topology/api/topology-api';
import { useTopologyEditor } from '@/features/topology/hooks/use-topology-editor';
import { ApiError } from '@/lib/api-client';
import { topologyKeys } from '@/lib/query-client';
import { EMPTY_DOCUMENT, type LinkIssue, type TopologyDocument } from '@/types/topology';

function SimulatorInner({
  topologyId,
  initialName,
  initialDocument,
  initialIssues,
}: {
  topologyId: string | null;
  initialName: string;
  initialDocument: TopologyDocument;
  initialIssues: LinkIssue[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);

  const { data: catalog = [] } = useQuery({
    queryKey: topologyKeys.catalog,
    queryFn: topologyApi.deviceCatalog,
    staleTime: Infinity, // static reference data
  });

  const editor = useTopologyEditor(initialDocument, catalog);
  const [name, setName] = useState(initialName);
  const [issues, setIssues] = useState<LinkIssue[]>(initialIssues);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      if (topologyId) {
        return topologyApi.update(topologyId, { name, document: editor.document });
      }
      return topologyApi.create(name, editor.document);
    },
    onSuccess: (saved) => {
      editor.markSaved();
      setIssues(saved.issues);
      setSavedAt(new Date());
      void queryClient.invalidateQueries({ queryKey: topologyKeys.list });
      if (!topologyId) {
        // Move to the saved topology's URL so a reload reopens it.
        void navigate(`/simulator/${saved.id}`, { replace: true });
      }
    },
  });

  /** Ask the server which ports and cable a new link should use. */
  const connect = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) =>
      topologyApi.suggestLink(editor.document, source, target),
    onSuccess: (suggestion, { source, target }) => {
      const link = editor.addLink({
        source: { deviceId: source, interface: suggestion.sourceInterface },
        target: { deviceId: target, interface: suggestion.targetInterface },
        cable: suggestion.cable,
        enabled: true,
        label: null,
      });
      if (suggestion.warning) {
        setIssues((current) => [
          ...current,
          { linkId: link.id, message: suggestion.warning as string },
        ]);
      }
    },
  });

  const handleConnect = useCallback(
    (source: string, target: string) => connect.mutate({ source, target }),
    [connect],
  );

  const handleExport = () => {
    const payload = {
      format: 'network-learning-platform/topology',
      schemaVersion: editor.document.schemaVersion,
      name,
      description: null,
      document: editor.document,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${name.replace(/[^\w-]+/g, '-').toLowerCase()}.topology.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text()) as {
        name?: string;
        document?: TopologyDocument;
      };
      if (!parsed.document) throw new Error('missing document');
      editor.replaceDocument(parsed.document);
      if (parsed.name) setName(parsed.name);
    } catch {
      // A malformed file is the user's mistake, not a crash. The server would
      // reject it on save anyway; this just avoids loading garbage onto canvas.
      window.alert('That file is not a valid topology export.');
    }
  };

  // Ctrl/Cmd+S to save, Ctrl/Cmd+Z / Shift+Z for history.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey)) return;
      if (event.key === 's') {
        event.preventDefault();
        save.mutate();
      }
      if (event.key === 'z') {
        event.preventDefault();
        if (event.shiftKey) editor.redo();
        else editor.undo();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [editor, save]);

  return (
    <div className="flex h-[calc(100dvh-8rem)] min-h-[540px] flex-col gap-3">
      <header className="flex flex-wrap items-center gap-3">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="Topology name"
          className="h-9 max-w-xs text-[14px] font-medium"
        />

        <span className="text-[12px] text-[var(--text-tertiary)]">
          {editor.isDirty ? (
            'Unsaved changes'
          ) : savedAt ? (
            <span className="flex items-center gap-1.5 text-[var(--color-success)]">
              <Check className="size-3.5" aria-hidden />
              Saved
            </span>
          ) : (
            `${editor.document.devices.length} devices`
          )}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={editor.undo}
            disabled={!editor.canUndo}
            aria-label="Undo"
          >
            <Undo2 className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={editor.redo}
            disabled={!editor.canRedo}
            aria-label="Redo"
          >
            <Redo2 className="size-4" />
          </Button>

          <Button
            variant="secondary"
            size="sm"
            leadingIcon={<Upload className="size-4" />}
            onClick={() => fileInput.current?.click()}
          >
            Import
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleImportFile(file);
              event.target.value = '';
            }}
          />

          <Button
            variant="secondary"
            size="sm"
            leadingIcon={<Download className="size-4" />}
            onClick={handleExport}
          >
            Export
          </Button>

          <Button
            size="sm"
            leadingIcon={<Save className="size-4" />}
            isLoading={save.isPending}
            onClick={() => save.mutate()}
          >
            Save
          </Button>
        </div>
      </header>

      {save.error instanceof ApiError && (
        <Alert tone="danger">
          {save.error.status === 422
            ? 'This topology has a structural problem the server rejected — check for cables to removed devices.'
            : save.error.message}
        </Alert>
      )}

      {connect.error instanceof ApiError && connect.error.code === 'no_free_interface' && (
        <Alert tone="warning">
          <span className="flex items-center gap-2">
            <TriangleAlert className="size-4 shrink-0" aria-hidden />
            That device has no free port of a compatible type.
          </span>
        </Alert>
      )}

      <TopologyWorkspace
        editor={editor}
        catalog={catalog}
        issues={issues}
        onConnect={handleConnect}
      />
    </div>
  );
}

export default function SimulatorPage() {
  const { topologyId } = useParams();

  const { data, isLoading, error } = useQuery({
    queryKey: topologyKeys.detail(topologyId ?? 'new'),
    queryFn: () => topologyApi.get(topologyId as string),
    enabled: Boolean(topologyId),
  });

  if (topologyId && isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading topology" />
      </div>
    );
  }

  if (topologyId && error) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert tone="danger" title="Topology not found">
          It may have been deleted, or belong to someone else.
        </Alert>
      </div>
    );
  }

  // Keyed on the id so switching topologies remounts the editor with fresh
  // state rather than leaking the previous document's history.
  return (
    <ReactFlowProvider>
      <SimulatorInner
        key={topologyId ?? 'new'}
        topologyId={topologyId ?? null}
        initialName={data?.name ?? 'Untitled topology'}
        initialDocument={data?.document ?? EMPTY_DOCUMENT}
        initialIssues={data?.issues ?? []}
      />
    </ReactFlowProvider>
  );
}
