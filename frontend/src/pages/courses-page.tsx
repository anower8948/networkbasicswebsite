import { motion } from 'motion/react';
import { BookOpen, Clock, GraduationCap, Layers, Lock, Network } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { useTracks } from '@/features/learning/hooks/use-catalog';
import { cn } from '@/lib/cn';
import type { CourseSummary, TrackLevel, TrackWithCourses } from '@/types/learning';

const TRACK_ICONS: Record<TrackLevel, typeof Layers> = {
  foundation: Layers,
  intermediate: Network,
  advanced: GraduationCap,
};

const TRACK_COLORS: Record<TrackLevel, string> = {
  foundation: 'var(--color-track-foundation)',
  intermediate: 'var(--color-track-intermediate)',
  advanced: 'var(--color-track-advanced)',
};

function CourseCard({ course, color }: { course: CourseSummary; color: string }) {
  return (
    <Link to={`/courses/${course.slug}`} className="block">
      <GlassPanel radius="xl" interactive className="flex h-full flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-title text-[15px] font-semibold">{course.title}</h3>
          {course.isEnrolled && (
            <span
              className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
              style={{
                backgroundColor: `color-mix(in oklab, ${color} 16%, transparent)`,
                color,
              }}
            >
              Enrolled
            </span>
          )}
        </div>

        {course.summary && (
          <p className="flex-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            {course.summary}
          </p>
        )}

        {course.isEnrolled && course.progressPercent !== null && (
          <div className="flex flex-col gap-1.5">
            <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-sunken)]">
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{ width: `${course.progressPercent}%`, backgroundColor: color }}
              />
            </div>
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {course.progressPercent}% complete
            </span>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-[var(--text-tertiary)]">
          <span className="flex items-center gap-1.5">
            <BookOpen className="size-3.5" aria-hidden />
            {course.lessonCount} lesson{course.lessonCount === 1 ? '' : 's'}
          </span>
          <span className="flex items-center gap-1.5">
            <Clock className="size-3.5" aria-hidden />
            {course.estimatedMinutes} min
          </span>
          <span className="capitalize">{course.difficulty}</span>
        </div>
      </GlassPanel>
    </Link>
  );
}

function TrackSection({ track, index }: { track: TrackWithCourses; index: number }) {
  const Icon = TRACK_ICONS[track.level];
  const color = TRACK_COLORS[track.level];

  return (
    <motion.section
      aria-label={track.title}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.08, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col gap-4"
    >
      <div className="flex items-start gap-3.5">
        <span
          className="flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
          style={{ backgroundColor: `color-mix(in oklab, ${color} 16%, transparent)` }}
        >
          <Icon className="size-5" style={{ color }} aria-hidden />
        </span>
        <div>
          <h2 className="text-title text-lg font-semibold">{track.title}</h2>
          {track.description && (
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[var(--text-secondary)]">
              {track.description}
            </p>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {track.courses.map((course) => (
          <CourseCard key={course.id} course={course} color={color} />
        ))}
      </div>
    </motion.section>
  );
}

/** Tracks that exist in the roadmap but have no published content yet. */
function ComingSoonTrack({ level, title, description }: {
  level: TrackLevel;
  title: string;
  description: string;
}) {
  const Icon = TRACK_ICONS[level];
  const color = TRACK_COLORS[level];

  return (
    <GlassPanel radius="xl" className={cn('flex items-start gap-3.5 p-5 opacity-70')}>
      <span
        className="flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
        style={{ backgroundColor: `color-mix(in oklab, ${color} 12%, transparent)` }}
      >
        <Icon className="size-5" style={{ color }} aria-hidden />
      </span>
      <div className="flex-1">
        <p className="text-title flex items-center gap-2 text-[15px] font-semibold">
          {title}
          <Lock className="size-3.5 text-[var(--text-tertiary)]" aria-hidden />
        </p>
        <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
          {description}
        </p>
      </div>
    </GlassPanel>
  );
}

export default function CoursesPage() {
  const { data: tracks, isLoading, error } = useTracks();

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8">
      <header>
        <h1 className="text-display text-[28px] leading-tight font-semibold">Courses</h1>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
          Work through the tracks in order, or jump to the topic you need.
        </p>
      </header>

      {error && <Alert tone="danger">Could not load the catalogue. Try reloading the page.</Alert>}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner size="lg" className="text-accent-500" label="Loading courses" />
        </div>
      ) : (
        <>
          {tracks?.map((track, index) => (
            <TrackSection key={track.id} track={track} index={index} />
          ))}

          <section aria-label="Coming soon" className="flex flex-col gap-3">
            <h2 className="text-title text-lg font-semibold">Coming next</h2>
            <ComingSoonTrack
              level="intermediate"
              title="Intermediate"
              description="VLANs, STP, EtherChannel, ACLs, OSPF, EIGRP, IPv6, wireless, QoS and security."
            />
            <ComingSoonTrack
              level="advanced"
              title="Advanced"
              description="Enterprise design, data centres, SDN, cloud and Azure networking, automation with Python."
            />
          </section>
        </>
      )}
    </div>
  );
}
