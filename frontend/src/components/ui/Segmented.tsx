import { ToggleGroup } from 'radix-ui'
import { cn } from '@/lib/cn'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
  disabled?: boolean
  title?: string
}

/** A single-choice segmented control. */
export function Segmented<T extends string>(props: {
  value: T
  onChange: (value: T) => void
  options: SegmentedOption<T>[]
  label: string
  className?: string
}) {
  const { value, onChange, options, label, className } = props
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      aria-label={label}
      onValueChange={(next) => {
        // Radix sends an empty string when the active item is pressed again; keep the choice.
        if (next) onChange(next as T)
      }}
      className={cn('border-hairline inline-flex rounded-lg border bg-black/25 p-0.5', className)}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          disabled={option.disabled}
          title={option.title}
          className="focus-ring text-text-2 data-[state=on]:text-text cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors duration-200 hover:text-white disabled:cursor-not-allowed disabled:opacity-45 data-[state=on]:bg-white/12"
        >
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  )
}
