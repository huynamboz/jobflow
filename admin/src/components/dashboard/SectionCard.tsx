import { ReactNode } from "react";
import { Card, CardBody } from "@heroui/card";
import { AlertCircle, Inbox, RefreshCcw } from "lucide-react";

interface SectionCardProps {
  title: string;
  description?: string;
  loading: boolean;
  error: Error | null;
  empty?: boolean;
  emptyMessage?: string;
  onRetry?: () => void;
  children: ReactNode;
  /** Extra action element rendered in the header right side (e.g. filter chip). */
  action?: ReactNode;
}

export default function SectionCard({
  title,
  description,
  loading,
  error,
  empty,
  emptyMessage = "No data yet",
  onRetry,
  children,
  action,
}: SectionCardProps) {
  return (
    <Card className="shadow-sm">
      <CardBody className="p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-default-900">{title}</h2>
            {description && (
              <p className="mt-0.5 text-xs text-default-500">{description}</p>
            )}
          </div>
          {action}
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-default-400" aria-live="polite">
            <span className="inline-block size-3 animate-pulse rounded-full bg-default-300" />
            Loading…
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col gap-2 rounded-lg border border-danger-100 bg-danger-50 p-3 text-sm text-danger-700">
            <div className="flex items-center gap-2">
              <AlertCircle className="size-4" />
              <span className="font-medium">Failed to load</span>
            </div>
            <p className="text-xs text-danger-600">{error.message}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1 self-start rounded-md border border-danger-200 bg-white px-2 py-1 text-xs font-medium text-danger-700 hover:bg-danger-100"
              >
                <RefreshCcw className="size-3" /> Retry
              </button>
            )}
          </div>
        )}

        {!loading && !error && empty && (
          <div className="flex flex-col items-center gap-2 py-8 text-sm text-default-400">
            <Inbox className="size-6" />
            <span>{emptyMessage}</span>
          </div>
        )}

        {!loading && !error && !empty && children}
      </CardBody>
    </Card>
  );
}
