"use client";

import { motion } from "framer-motion";
import type { FollowUpChip } from "@/lib/api";

type FollowUpChipsProps = {
  items: FollowUpChip[];
  disabled?: boolean;
  onSelect: (prompt: string) => void;
};

export function FollowUpChips({
  items,
  disabled = false,
  onSelect,
}: FollowUpChipsProps) {
  if (!items.length) return null;

  return (
    <div className="mt-2 flex max-w-[min(100%,42rem)] flex-wrap gap-1.5">
      {items.map((item, index) => (
        <motion.button
          key={item.id}
          type="button"
          disabled={disabled}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18, delay: index * 0.04 }}
          onClick={() => onSelect(item.prompt)}
          className="rounded-full border border-[var(--line)] bg-[var(--surface-2)] px-3 py-1 text-xs text-[var(--ink-soft)] shadow-[var(--shadow-soft)] transition-all duration-200 hover:border-[var(--accent)]/50 hover:bg-[var(--accent-soft)] hover:text-[var(--accent-deep)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {item.label}
        </motion.button>
      ))}
    </div>
  );
}
