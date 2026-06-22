import * as React from "react"
import { cn } from "@/lib/utils"
import { ClassificationTag } from "@/lib/api/types"

interface IntelBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tag: ClassificationTag
  size?: "sm" | "md" | "lg"
}

const tagStyles: Record<ClassificationTag, { border: string; text: string; bg: string; label: string }> = {
  public_osint: {
    border: "border-intel-cyan/30",
    text: "text-intel-cyan",
    bg: "bg-intel-cyan-dim/15",
    label: "OSINT // PUBLIC"
  },
  case_sensitive: {
    border: "border-intel-amber/30",
    text: "text-intel-amber",
    bg: "bg-intel-amber-dim/15",
    label: "RESTRICTED // SENSITIVE"
  },
  pii: {
    border: "border-intel-magenta/30",
    text: "text-intel-magenta",
    bg: "bg-intel-magenta-dim/15",
    label: "PII // SECURE"
  },
  evidentiary: {
    border: "border-intel-red/30",
    text: "text-intel-red",
    bg: "bg-intel-red-dim/15",
    label: "EVIDENTIARY"
  },
  legal_privileged: {
    border: "border-intel-purple/30",
    text: "text-intel-purple",
    bg: "bg-intel-purple-dim/15",
    label: "LEGAL // PRIVILEGED"
  }
}

const IntelBadge = React.forwardRef<HTMLSpanElement, IntelBadgeProps>(
  ({ className, tag, size = "md", ...props }, ref) => {
    const config = tagStyles[tag] || tagStyles.case_sensitive

    const paddingClasses = {
      sm: "px-2 py-0.5 text-[9px] tracking-wider",
      md: "px-2.5 py-0.5 text-[10px] tracking-widest",
      lg: "px-3 py-1 text-xs tracking-widest"
    }

    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center rounded border font-mono font-bold select-none uppercase transition-all duration-200",
          config.border,
          config.text,
          config.bg,
          paddingClasses[size],
          className
        )}
        {...props}
      >
        {config.label}
      </span>
    )
  }
)
IntelBadge.displayName = "IntelBadge"

export { IntelBadge }
