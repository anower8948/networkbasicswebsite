/**
 * Notes and the bookmark toggle, in the lesson they belong to.
 *
 * Notes are most useful written where the thought occurred, so this sits at the
 * foot of the lesson rather than only on the notes page. The star and the note
 * box share a row because they answer the same question — "I want to come back
 * to this" — with different amounts of effort.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bookmark, BookmarkCheck, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { notesApi } from '../api/notes-api';
import { notesKeys } from '@/lib/query-client';

interface LessonNotesProps {
  lessonId: string;
}

export function LessonNotes({ lessonId }: LessonNotesProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState('');

  const notes = useQuery({
    queryKey: notesKeys.forLesson(lessonId),
    queryFn: () => notesApi.forLesson(lessonId),
  });

  const bookmarks = useQuery({
    queryKey: notesKeys.bookmarks,
    queryFn: notesApi.bookmarks,
  });

  const isBookmarked = (bookmarks.data ?? []).some((item) => item.lessonId === lessonId);

  const refreshNotes = () => {
    void queryClient.invalidateQueries({ queryKey: notesKeys.forLesson(lessonId) });
    // The all-notes page is a different key and would otherwise go stale.
    void queryClient.invalidateQueries({ queryKey: notesKeys.all });
  };

  const addNote = useMutation({
    mutationFn: () => notesApi.create(lessonId, draft.trim()),
    onSuccess: () => {
      setDraft('');
      refreshNotes();
    },
  });

  const removeNote = useMutation({
    mutationFn: (noteId: string) => notesApi.remove(noteId),
    onSuccess: refreshNotes,
  });

  const toggleBookmark = useMutation({
    mutationFn: () => notesApi.toggleBookmark(lessonId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: notesKeys.bookmarks }),
  });

  return (
    <section aria-label="Your notes" className="hairline-t flex flex-col gap-4 pt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-title text-lg font-semibold">Your notes</h2>
        <Button
          variant="ghost"
          size="sm"
          isLoading={toggleBookmark.isPending}
          leadingIcon={
            isBookmarked ? (
              <BookmarkCheck className="size-4 text-accent-500" />
            ) : (
              <Bookmark className="size-4" />
            )
          }
          onClick={() => toggleBookmark.mutate()}
        >
          {isBookmarked ? 'Saved' : 'Save this lesson'}
        </Button>
      </div>

      {(notes.data ?? []).length > 0 && (
        <ul className="flex flex-col gap-2">
          {notes.data?.map((note) => (
            <li key={note.id}>
              <GlassPanel radius="lg" className="flex items-start gap-3 p-4">
                <p className="min-w-0 flex-1 text-[14px] leading-relaxed whitespace-pre-wrap">
                  {note.body}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Delete note"
                  onClick={() => removeNote.mutate(note.id)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </GlassPanel>
            </li>
          ))}
        </ul>
      )}

      <GlassPanel radius="lg" className="flex flex-col gap-3 p-4">
        <label htmlFor="new-note" className="sr-only">
          Write a note
        </label>
        <textarea
          id="new-note"
          rows={3}
          value={draft}
          placeholder="Write something down while it is fresh…"
          onChange={(event) => setDraft(event.target.value)}
          className="glass-inset resize-y rounded-[var(--radius-sm)] px-3 py-2 text-[14px] leading-relaxed focus:border-accent-500 focus:outline-none"
        />
        <Button
          size="sm"
          className="self-end"
          disabled={!draft.trim()}
          isLoading={addNote.isPending}
          onClick={() => addNote.mutate()}
        >
          Save note
        </Button>
      </GlassPanel>
    </section>
  );
}
