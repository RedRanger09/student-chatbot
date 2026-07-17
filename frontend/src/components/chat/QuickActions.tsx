"use client";

import { motion } from "framer-motion";
import { QUICK_ACTIONS } from "@/lib/quick-actions";
import { Card } from "@/components/ui/card";

type QuickActionsProps = {
  onSelect: (prompt: string) => void;
  compact?: boolean;
};

export function QuickActions({ onSelect, compact = false }: QuickActionsProps) {
  if (compact) {
    return (
      <div className="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <motion.button
              key={action.id}
              type="button"
              whileHover={{ y: -1 }}
              transition={{ duration: 0.2 }}
              onClick={() => onSelect(action.prompt)}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium text-[var(--ink-soft)] shadow-[var(--shadow-soft)] transition-all duration-200 hover:border-[var(--accent)]/50 hover:bg-[var(--accent-soft)] hover:text-[var(--accent-deep)]"
            >
              <Icon className="h-3.5 w-3.5" />
              {action.label}
            </motion.button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="grid max-h-[320px] grid-cols-2 gap-2.5 overflow-y-auto pr-1 sm:grid-cols-3 lg:grid-cols-4">
      {QUICK_ACTIONS.map((action, index) => {
        const Icon = action.icon;
        return (
          <motion.button
            key={action.id}
            type="button"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, delay: Math.min(index * 0.02, 0.2) }}
            whileHover={{ y: -2 }}
            onClick={() => onSelect(action.prompt)}
            className="text-left"
          >
            <Card className="h-full cursor-pointer p-3 shadow-[var(--shadow-soft)] transition-all duration-200 hover:border-[var(--accent)]/45 hover:bg-[var(--accent-soft)] hover:shadow-[var(--shadow)]">
              <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--surface-2)] text-[var(--accent-deep)]">
                <Icon className="h-4 w-4" />
              </div>
              <p className="text-sm font-semibold text-[var(--ink)]">{action.label}</p>
              <p className="mt-0.5 text-xs leading-snug text-[var(--muted)]">{action.description}</p>
            </Card>
          </motion.button>
        );
      })}
    </div>
  );
}
