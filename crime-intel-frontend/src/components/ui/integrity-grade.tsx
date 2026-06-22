import * as React from "react"
import { cn } from "@/lib/utils"
import { ShieldCheck, ShieldAlert, Shield, AlertTriangle } from "lucide-react"

export type IntegrityGradeType = "A" | "B" | "C" | "D" | "F"

interface IntegrityGradeProps extends React.HTMLAttributes<HTMLDivElement> {
  grade: IntegrityGradeType
  showDescription?: boolean
  size?: "sm" | "md" | "lg"
}

const gradeStyles = {
  A: {
    border: "border-intel-green/30 bg-intel-green-dim/15 text-intel-green hover:bg-intel-green-dim/30",
    glow: "shadow-[0_0_10px_rgba(45,212,191,0.15)]",
    icon: ShieldCheck,
    label: "A - Tamper-free",
    desc: "Cryptographically verified, complete chain of custody."
  },
  B: {
    border: "border-intel-cyan/30 bg-intel-cyan-dim/15 text-intel-cyan hover:bg-intel-cyan-dim/30",
    glow: "",
    icon: ShieldCheck,
    label: "B - Secure",
    desc: "Cryptographically verified, minor metadata gaps."
  },
  C: {
    border: "border-intel-amber/30 bg-intel-amber-dim/15 text-intel-amber hover:bg-intel-amber-dim/30",
    glow: "",
    icon: Shield,
    label: "C - Incomplete Chain",
    desc: "Cryptographic hash correct, but gaps in custody logs."
  },
  D: {
    border: "border-intel-purple/30 bg-intel-purple-dim/15 text-intel-purple hover:bg-intel-purple-dim/30",
    glow: "",
    icon: AlertTriangle,
    label: "D - Unverified Chain",
    desc: "Missing custody records or untrusted source."
  },
  F: {
    border: "border-intel-red/40 bg-intel-red-dim/20 text-intel-red hover:bg-intel-red-dim/30 animate-pulse",
    glow: "shadow-[0_0_12px_rgba(244,63,94,0.25)]",
    icon: ShieldAlert,
    label: "F - Tamper Alert",
    desc: "Cryptographic hash mismatch or broken chain!"
  }
}

const IntegrityGrade = React.forwardRef<HTMLDivElement, IntegrityGradeProps>(
  ({ className, grade, showDescription = false, size = "md", ...props }, ref) => {
    const config = gradeStyles[grade] || gradeStyles.D
    const Icon = config.icon

    const paddingClasses = {
      sm: "px-2 py-0.5 text-[10px] gap-1",
      md: "px-2.5 py-1 text-xs gap-1.5",
      lg: "px-3.5 py-1.5 text-sm gap-2"
    }

    return (
      <div ref={ref} className={cn("inline-flex flex-col gap-1", className)} {...props}>
        <div
          className={cn(
            "inline-flex items-center rounded-full border font-mono font-bold transition-all duration-200 select-none",
            config.border,
            config.glow,
            paddingClasses[size]
          )}
        >
          <Icon className={cn(
            size === "sm" ? "w-3 h-3" : size === "md" ? "w-3.5 h-3.5" : "w-4 h-4"
          )} />
          <span>{size === "sm" ? grade : config.label}</span>
        </div>
        {showDescription && (
          <span className="text-[11px] text-text-secondary font-sans leading-tight mt-0.5">
            {config.desc}
          </span>
        )}
      </div>
    )
  }
)
IntegrityGrade.displayName = "IntegrityGrade"

export { IntegrityGrade }
