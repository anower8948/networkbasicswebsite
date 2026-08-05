/** Notes and bookmarks. */

import { apiClient } from '@/lib/api-client';
import type { Bookmark, Note, NoteWithContext } from '@/types/notes';

export const notesApi = {
  all: () => apiClient.get<NoteWithContext[]>('/notes'),

  forLesson: (lessonId: string) => apiClient.get<Note[]>(`/notes/lesson/${lessonId}`),

  create: (lessonId: string, body: string, blockIndex?: number) =>
    apiClient.post<Note>('/notes', { lessonId, body, blockIndex: blockIndex ?? null }),

  update: (noteId: string, changes: { body?: string; isPinned?: boolean }) =>
    apiClient.patch<Note>(`/notes/${noteId}`, changes),

  remove: (noteId: string) => apiClient.delete<{ message: string }>(`/notes/${noteId}`),

  bookmarks: () => apiClient.get<Bookmark[]>('/bookmarks'),

  /** One endpoint both ways, because the UI is a single star. */
  toggleBookmark: (lessonId: string) =>
    apiClient.post<{ message: string }>('/bookmarks', { lessonId }),
};
