"use client";

import { motion } from "framer-motion";
import {
  HeartHandshake,
  Phone,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export type SupportResource = {
  id?: string;
  name: string;
  office?: string;
  email?: string;
  phone?: string;
  office_hours?: string;
  emergency_notice?: string | null;
};

type SupportResourcesCardProps = {
  resource: SupportResource;
  categoryLabel?: string | null;
  severity?: string | null;
};

function severityClass(severity?: string | null): string {
  const value = (severity || "").toUpperCase();
  if (value === "CRITICAL") {
    return "border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-100";
  }
  if (value === "HIGH") {
    return "border-orange-200 bg-orange-50 text-orange-800 dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-100";
  }
  if (value === "MEDIUM") {
    return "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100";
  }
  return "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100";
}

export function SupportResourcesCard({
  resource,
  categoryLabel,
  severity,
}: SupportResourcesCardProps) {
  const showEmergency = Boolean(resource.emergency_notice);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="mt-3 w-full max-w-[min(100%,42rem)] space-y-2"
    >
      {showEmergency ? (
        <Alert className="border-red-200 bg-red-50 text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-100">
          <AlertTitle className="flex items-center gap-1.5 text-red-900 dark:text-red-100">
            <TriangleAlert className="h-4 w-4" />
            Emergency notice
          </AlertTitle>
          <AlertDescription className="text-red-800 dark:text-red-100/90">
            {resource.emergency_notice}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="border-[var(--accent)]/30 shadow-none">
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4 text-[var(--accent-deep)]" />
              Support Resources
            </CardTitle>
            {categoryLabel ? (
              <Badge className="gap-1">
                <HeartHandshake className="h-3 w-3" />
                {categoryLabel}
              </Badge>
            ) : null}
            {severity ? (
              <Badge className={severityClass(severity)}>{severity}</Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              Support office
            </p>
            <p className="mt-0.5 font-medium text-[var(--ink)]">{resource.name}</p>
            {resource.office ? (
              <p className="text-[var(--muted)]">{resource.office}</p>
            ) : null}
          </div>

          <Separator />

          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Office hours
              </p>
              <p className="mt-0.5 text-[var(--ink-soft)]">
                {resource.office_hours || "—"}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Email
              </p>
              <p className="mt-0.5 text-[var(--ink-soft)]">{resource.email || "—"}</p>
            </div>
            <div className="sm:col-span-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Phone
              </p>
              <p className="mt-0.5 flex items-center gap-1.5 text-[var(--ink-soft)]">
                <Phone className="h-3.5 w-3.5" />
                {resource.phone || "—"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function extractSupportResource(
  meta?: Record<string, unknown> | null,
): SupportResource | null {
  if (!meta) return null;
  const raw = meta.support_resource;
  if (!raw || typeof raw !== "object") return null;
  const resource = raw as SupportResource;
  if (!resource.name) return null;
  return resource;
}
