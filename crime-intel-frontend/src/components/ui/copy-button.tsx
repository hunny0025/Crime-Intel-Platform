import * as React from "react"
import { cn } from "@/lib/utils"
import { Copy, Check } from "lucide-react"

interface CopyButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string
}

const CopyButton = React.forwardRef<HTMLButtonElement, CopyButtonProps>(
  ({ className, value, ...props }, ref) => {
    const [copied, setCopied] = React.useState(false)

    const handleCopy = async (e: React.MouseEvent) => {
      e.stopPropagation()
      try {
        await navigator.clipboard.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch (err) {
        console.error("Failed to copy text: ", err)
      }
    }

    return (
      <button
        ref={ref}
        type="button"
        onClick={handleCopy}
        className={cn(
          "inline-flex items-center justify-center rounded-md text-xs font-medium transition-colors hover:bg-elevated hover:text-text-primary text-text-secondary h-7 w-7 border border-border-subtle",
          className
        )}
        title={copied ? "Copied!" : "Copy to clipboard"}
        {...props}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-intel-green" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
    )
  }
)
CopyButton.displayName = "CopyButton"

export { CopyButton }
