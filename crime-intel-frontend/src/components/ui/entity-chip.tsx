import * as React from "react"
import { cn } from "@/lib/utils"
import { 
  User, Laptop, AtSign, MapPin, Calendar, 
  Brain, AlertOctagon, HelpCircle, FileText 
} from "lucide-react"

export type EntityType = 
  | "Person" 
  | "Device" 
  | "Account" 
  | "Location" 
  | "Event" 
  | "Hypothesis" 
  | "Contradiction" 
  | "EvidenceGap"
  | "Artifact"
  | "Organization"

interface EntityChipProps extends React.HTMLAttributes<HTMLDivElement> {
  type: EntityType
  label: string
  clickable?: boolean
  active?: boolean
}

const entityConfigs = {
  Person: {
    border: "border-intel-blue/20 hover:border-intel-blue/50",
    bg: "bg-intel-blue-dim/10 text-intel-blue hover:bg-intel-blue-dim/20",
    activeBg: "bg-intel-blue text-obsidian font-semibold border-intel-blue",
    icon: User
  },
  Device: {
    border: "border-intel-purple/20 hover:border-intel-purple/50",
    bg: "bg-intel-purple-dim/10 text-intel-purple hover:bg-intel-purple-dim/20",
    activeBg: "bg-intel-purple text-obsidian font-semibold border-intel-purple",
    icon: Laptop
  },
  Account: {
    border: "border-intel-cyan/20 hover:border-intel-cyan/50",
    bg: "bg-intel-cyan-dim/10 text-intel-cyan hover:bg-intel-cyan-dim/20",
    activeBg: "bg-intel-cyan text-obsidian font-semibold border-intel-cyan",
    icon: AtSign
  },
  Location: {
    border: "border-intel-green/20 hover:border-intel-green/50",
    bg: "bg-intel-green-dim/10 text-intel-green hover:bg-intel-green-dim/20",
    activeBg: "bg-intel-green text-obsidian font-semibold border-intel-green",
    icon: MapPin
  },
  Event: {
    border: "border-intel-amber/20 hover:border-intel-amber/50",
    bg: "bg-intel-amber-dim/10 text-intel-amber hover:bg-intel-amber-dim/20",
    activeBg: "bg-intel-amber text-obsidian font-semibold border-intel-amber",
    icon: Calendar
  },
  Hypothesis: {
    border: "border-intel-magenta/20 hover:border-intel-magenta/50",
    bg: "bg-intel-magenta-dim/10 text-intel-magenta hover:bg-intel-magenta-dim/20",
    activeBg: "bg-intel-magenta text-obsidian font-semibold border-intel-magenta",
    icon: Brain
  },
  Contradiction: {
    border: "border-intel-red/20 hover:border-intel-red/50",
    bg: "bg-intel-red-dim/10 text-intel-red hover:bg-intel-red-dim/20",
    activeBg: "bg-intel-red text-obsidian font-semibold border-intel-red",
    icon: AlertOctagon
  },
  EvidenceGap: {
    border: "border-intel-amber/20 hover:border-intel-amber/50",
    bg: "bg-intel-amber-dim/10 text-intel-amber hover:bg-intel-amber-dim/20",
    activeBg: "bg-intel-amber text-obsidian font-semibold border-intel-amber",
    icon: HelpCircle
  },
  Artifact: {
    border: "border-intel-blue/20 hover:border-intel-blue/50",
    bg: "bg-intel-blue-dim/10 text-intel-blue hover:bg-intel-blue-dim/20",
    activeBg: "bg-intel-blue text-obsidian font-semibold border-intel-blue",
    icon: FileText
  },
  Organization: {
    border: "border-intel-cyan/20 hover:border-intel-cyan/50",
    bg: "bg-intel-cyan-dim/10 text-intel-cyan hover:bg-intel-cyan-dim/20",
    activeBg: "bg-intel-cyan text-obsidian font-semibold border-intel-cyan",
    icon: MapPin // Reuse map pin or something similar for Org
  }
}

const EntityChip = React.forwardRef<HTMLDivElement, EntityChipProps>(
  ({ className, type, label, clickable = true, active = false, ...props }, ref) => {
    const config = entityConfigs[type] || entityConfigs.Person
    const Icon = config.icon

    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1 rounded-md border text-xs font-mono font-medium transition-all duration-200 select-none",
          active ? config.activeBg : cn(config.border, config.bg),
          clickable && "cursor-pointer active:scale-95",
          className
        )}
        {...props}
      >
        <Icon className="w-3.5 h-3.5 shrink-0" />
        <span className="truncate max-w-[150px]">{label}</span>
      </div>
    )
  }
)
EntityChip.displayName = "EntityChip"

export { EntityChip }
