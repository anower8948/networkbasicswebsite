/** Notes and bookmarks — mirrors `app/schemas/notes.py`. */

export interface Note {
  id: string;
  lessonId: string;
  body: string;
  blockIndex: number | null;
  isPinned: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface NoteWithContext extends Note {
  lessonTitle: string;
  lessonSlug: string;
  courseSlug: string;
}

export interface Bookmark {
  id: string;
  lessonId: string;
  label: string | null;
  lessonTitle: string;
  lessonSlug: string;
  courseSlug: string;
  createdAt: string;
}
