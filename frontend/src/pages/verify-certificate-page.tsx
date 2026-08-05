/**
 * Public certificate verification.
 *
 * Reached from a link on a CV, by someone who has no account and never will.
 * So: no app shell, no navigation, no sign-in prompt — one page that answers
 * one question. It renders standalone for the same reason the endpoint is
 * unauthenticated.
 */

import { useQuery } from '@tanstack/react-query';
import { BadgeCheck, ShieldAlert, ShieldX } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Input } from '@/components/ui/input';
import { Logo } from '@/components/ui/logo';
import { Spinner } from '@/components/ui/spinner';
import { gamificationApi } from '@/features/gamification/api/gamification-api';

function Result({ code }: { code: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['certificate-verification', code],
    queryFn: () => gamificationApi.verifyCertificate(code),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner size="lg" className="text-accent-500" label="Checking certificate" />
      </div>
    );
  }

  // A network failure is not the same as "not valid", and saying so would be a
  // lie about someone's credential.
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <ShieldAlert className="size-10 text-[var(--color-warning)]" aria-hidden />
        <p className="text-[15px] font-medium">This could not be checked right now</p>
        <p className="text-[13px] text-[var(--text-secondary)]">
          Something went wrong reaching the service. Please try again shortly.
        </p>
      </div>
    );
  }

  if (!data?.valid) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <ShieldX className="size-10 text-[var(--color-danger)]" aria-hidden />
        <p className="text-[15px] font-medium">
          {data?.revoked ? 'This certificate has been revoked' : 'No matching certificate'}
        </p>
        <p className="text-[13px] text-[var(--text-secondary)]">
          {data?.revoked
            ? 'It was issued but is no longer valid.'
            : 'Check the code and try again.'}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <BadgeCheck className="size-12 text-[var(--color-success)]" aria-hidden />
      <p className="text-[15px] font-medium text-[var(--color-success)]">
        Verified certificate
      </p>
      <div>
        <p className="text-title text-xl font-semibold">{data.recipientName}</p>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          completed <strong>{data.courseTitle}</strong>
        </p>
        {data.issuedAt && (
          <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">
            Issued {new Date(data.issuedAt).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
  );
}

export default function VerifyCertificatePage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [entered, setEntered] = useState('');

  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="flex w-full max-w-md flex-col gap-6">
        <div className="flex justify-center">
          <Logo />
        </div>

        <GlassPanel radius="2xl" className="p-8">
          <h1 className="text-title text-center text-lg font-semibold">
            Certificate verification
          </h1>

          {code ? (
            <Result code={code} />
          ) : (
            <form
              className="mt-6 flex flex-col gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                const trimmed = entered.trim();
                if (trimmed) void navigate(`/verify/${trimmed}`);
              }}
            >
              <Input
                label="Verification code"
                value={entered}
                placeholder="Paste the code from the certificate"
                onChange={(event) => setEntered(event.target.value)}
                className="font-mono"
              />
              <Button type="submit" fullWidth disabled={!entered.trim()}>
                Check it
              </Button>
            </form>
          )}
        </GlassPanel>

        <p className="text-center text-[12px] text-[var(--text-tertiary)]">
          Certificates are issued by the Network Learning Platform.
        </p>
      </div>
    </div>
  );
}
