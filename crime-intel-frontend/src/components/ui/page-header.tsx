import * as React from "react"
import { cn } from "@/lib/utils"

interface PageHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string
  description?: string
  actions?: React.ReactNode
}

const PageHeader = React.forwardRef<HTMLDivElement, PageHeaderProps>(
  ({ className, title, description, actions, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "flex flex-col md:flex-row md:items-center md:justify-between pb-6 border-b border-border-subtle/50 gap-4 mb-6",
          className
        )}
        {...props}
      >
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-text-primary font-sans flex items-center gap-2">
            {title}
          </h1>
          {description && (
            <p className="text-sm text-text-secondary font-sans max-w-2xl leading-relaxed">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-3 shrink-0">
            {actions}
          </div>
        )}
      </div>
    )
  }
)
PageHeader.displayName = "PageHeader"

export { PageHeader }
