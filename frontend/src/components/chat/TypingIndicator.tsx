"use client";

import { motion } from "framer-motion";

export function TypingIndicator() {
  return (
    <div
      className="flex items-center gap-1.5 px-0.5 py-1.5"
      role="status"
      aria-live="polite"
      aria-label="Assistant is typing"
    >
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{
            duration: 0.9,
            repeat: Infinity,
            delay: i * 0.14,
            ease: "easeInOut",
          }}
        />
      ))}
      <span className="sr-only">Assistant is typing</span>
    </div>
  );
}
