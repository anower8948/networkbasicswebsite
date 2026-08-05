/**
 * Notes and saved lessons.
 *
 * Every note links back to the lesson it was written against — which is why the
 * API returns the course and lesson slugs alongside each note rather than
 * making this page resolve them one by one.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bookmark as BookmarkIcon, Pin, PinOff, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { notesApi } from '@/features/notes/api/notes-api';
import { notesKeys } from '@/lib/query-client';
import { cn } from '@/lib/cn';
import type { NoteWithContext } from '@/types/notes';

function NoteCard({ note }: { note: NoteWithContext }) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: notesKeys.all });

  const pin = useMutation({
    mutationFn: () => notesApi.update(note.id, { isPinned: !note.isPinned }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: () => notesApi.remove(note.id),
    onSuccess: invalidate,
  });

  return (
    <GlassPanel
      radius="lg"
      className={cn('flex flex-col gap-2 p-4', note.isPinned && 'ring-1 ring-accent-500/30')}
    >
      <div className="flex items-start justify-between gap-2">
        <Link
          to={`/courses/${note.courseSlug}/${note.lessonSlug}`}
          className="text-[12px] font-medium text-accent-500 hover:underline"
        >
          {note.lessonTitle}
        </Link>
        <div className="flex shrink-0 gap-0.5">
          <Button
            variant="ghost"
            size="sm"
            aria-label={note.isPinned ? 'Unpin note' : 'Pin note'}
            isLoading={pin.isPending}
            onClick={() => pin.mutate()}
          >
            {note.isPinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label="Delete note"
            isLoading={remove.isPending}
            onClick={() => remove.mutate()}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      <p className="text-[13px] leading-relaxed whitespace-pre-wrap">{note.body}</p>

      <p className="text-[11px] text-[var(--text-tertiary)]">
        {new Date(note.updatedAt).toLocaleDateString()}
      </p>
    </GlassPanel>
  );
}

export default function NotesPage() {
  const [tab, setTab] = useState<'notes' | 'bookmarks'>('notes');

  const notes = useQuery({ queryKey: notesKeys.all, queryFn: notesApi.all });
  const bookmarks = useQuery({
    queryKey: notesKeys.bookmarks,
    queryFn: notesApi.bookmarks,
    enabled: tab === 'bookmarks',
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-title text-2xl font-semibold">Your notes</h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Everything you have written down, and the lessons you saved.
        </p>
      </header>

      <div role="tablist" aria-label="Notes and bookmarks" className="flex gap-1">
        {(['notes', 'bookmarks'] as const).map((item) => (
          <button
            key={item}
            role="tab"
            type="button"
            aria-selected={tab === item}
            onClick={() => setTab(item)}
            className={cn(
              'rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] font-medium capitalize',
              tab === item
                ? 'bg-accent-500/12 text-accent-600 dark:text-accent-300'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]',
            )}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === 'notes' &&
        (notes.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" className="text-accent-500" label="Loading notes" />
          </div>
        ) : notes.data && notes.data.length > 0 ? (
          <div className="flex flex-col gap-3">
            {notes.data.map((note) => (
              <NoteCard key={note.id} note={note} />
            ))}
          </div>
        ) : (
          <Alert tone="info" title="No notes yet">
            Write one from inside any lesson and it will appear here.
          </Alert>
        ))}

      {tab === 'bookmarks' &&
        (bookmarks.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" className="text-accent-500" label="Loading bookmarks" />
          </div>
        ) : bookmarks.data && bookmarks.data.length > 0 ? (
          <div className="flex flex-col gap-2">
            {bookmarks.data.map((bookmark) => (
              <Link
                key={bookmark.id}
                to={`/courses/${bookmark.courseSlug}/${bookmark.lessonSlug}`}
              >
                <GlassPanel
                  radius="lg"
                  interactive
                  className="flex items-center gap-3 px-4 py-3"
                >
                  <BookmarkIcon className="size-4 shrink-0 text-accent-500" aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-[14px] font-medium">
                    {bookmark.lessonTitle}
                  </span>
                  <span className="shrink-0 text-[12px] text-[var(--text-tertiary)]">
                    {new Date(bookmark.createdAt).toLocaleDateString()}
                  </span>
                </GlassPanel>
              </Link>
            ))}
          </div>
        ) : (
          <Alert tone="info" title="Nothing saved yet">
            Bookmark a lesson to come back to it quickly.
          </Alert>
        ))}
    </div>
  );
}
