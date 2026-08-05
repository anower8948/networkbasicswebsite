/**
 * Certificates the learner holds.
 *
 * Each card shows the verification link rather than hiding it behind a button,
 * because the link *is* the artefact — it is what gets pasted into a CV or a
 * LinkedIn profile, and it should be as easy to copy as the serial is to read.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Award, Check, Copy, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Spinner } from '@/components/ui/spinner';
import { gamificationApi } from '@/features/gamification/api/gamification-api';
import { learningApi } from '@/features/learning/api/learning-api';
import { ApiError } from '@/lib/api-client';
import { gamificationKeys, learningKeys } from '@/lib/query-client';
import type { Certificate } from '@/types/gamification';

function CertificateCard({ certificate }: { certificate: Certificate }) {
  const [copied, setCopied] = useState(false);
  const url = `${window.location.origin}/verify/${certificate.verificationCode}`;

  const copy = async () => {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <GlassPanel radius="xl" className="flex flex-col gap-4 p-6">
      <div className="flex items-start gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-accent-500/15 text-accent-500">
          <Award className="size-6" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-title text-[16px] font-semibold">{certificate.courseTitle}</h3>
          <p className="mt-0.5 text-[13px] text-[var(--text-secondary)]">
            Issued to {certificate.recipientName} on{' '}
            {new Date(certificate.issuedAt).toLocaleDateString()}
          </p>
          <p className="mt-1 font-mono text-[12px] text-[var(--text-tertiary)]">
            {certificate.serial}
          </p>
        </div>
        {certificate.revokedAt && (
          <span className="shrink-0 rounded-full bg-[var(--color-danger)]/15 px-2 py-0.5 text-[11px] font-medium text-[var(--color-danger)]">
            Revoked
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-[var(--radius-xs)] bg-[var(--surface-sunken)] px-2.5 py-1.5 font-mono text-[12px]">
          {url}
        </code>
        <Button
          variant="secondary"
          size="sm"
          leadingIcon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          onClick={() => void copy()}
        >
          {copied ? 'Copied' : 'Copy link'}
        </Button>
        <Link to={`/verify/${certificate.verificationCode}`}>
          <Button variant="ghost" size="sm" leadingIcon={<ExternalLink className="size-3.5" />}>
            View
          </Button>
        </Link>
      </div>
    </GlassPanel>
  );
}

export default function CertificatesPage() {
  const queryClient = useQueryClient();

  const certificates = useQuery({
    queryKey: gamificationKeys.certificates,
    queryFn: gamificationApi.certificates,
  });

  const enrollments = useQuery({
    queryKey: learningKeys.enrollments,
    queryFn: learningApi.enrollments,
  });

  const claim = useMutation({
    mutationFn: (slug: string) => gamificationApi.claimCertificate(slug),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: gamificationKeys.certificates }),
  });

  if (certificates.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" className="text-accent-500" label="Loading certificates" />
      </div>
    );
  }

  const held = new Set((certificates.data ?? []).map((item) => item.courseId));
  // Courses finished but not yet claimed. `grantsCertificate` is authored per
  // course, so a completed course without one simply never appears here.
  const claimable = (enrollments.data ?? []).filter(
    (enrollment) =>
      enrollment.status === 'completed' &&
      enrollment.course.grantsCertificate &&
      !held.has(enrollment.course.id),
  );

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-title text-2xl font-semibold">Certificates</h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Every certificate carries a verification link anyone can check.
        </p>
      </header>

      {claim.error instanceof ApiError && (
        <Alert tone="danger">{claim.error.message}</Alert>
      )}

      {claimable.length > 0 && (
        <div className="flex flex-col gap-3">
          {claimable.map((enrollment) => (
            <Alert key={enrollment.course.id} tone="success">
              <span className="flex flex-wrap items-center gap-3">
                <span className="flex-1">
                  You finished <strong>{enrollment.course.title}</strong>. Your certificate
                  is ready.
                </span>
                <Button
                  size="sm"
                  isLoading={claim.isPending}
                  onClick={() => claim.mutate(enrollment.course.slug)}
                >
                  Claim it
                </Button>
              </span>
            </Alert>
          ))}
        </div>
      )}

      {certificates.data && certificates.data.length > 0 ? (
        <div className="flex flex-col gap-4">
          {certificates.data.map((certificate) => (
            <CertificateCard key={certificate.id} certificate={certificate} />
          ))}
        </div>
      ) : (
        claimable.length === 0 && (
          <Alert tone="info" title="No certificates yet">
            Finish a course that awards one and it will appear here.{' '}
            <Link to="/courses" className="underline">
              Browse courses
            </Link>
            .
          </Alert>
        )
      )}
    </div>
  );
}
