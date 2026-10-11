import { Switch as Primitive } from 'radix-ui'
import { cn } from '@/lib/cn'

export function Switch(props: {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: string
  accent?: 'official' | 'ember' | 'neutral'
  disabled?: boolean
}) {
  const { checked, onCheckedChange, label, accent = 'neutral', disabled = false } = props
  const on = {
    official: 'data-[state=checked]:bg-official/80',
    ember: 'data-[state=checked]:bg-ember/85',
    neutral: 'data-[state=checked]:bg-text/60',
  }[accent]
  return (
    <Primitive.Root
      checked={checked}
      disabled={disabled}
      onCheckedChange={onCheckedChange}
      aria-label={label}
      className={cn(
        'focus-ring relative h-5 w-9 shrink-0 cursor-pointer rounded-full bg-white/12 transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40',
        on,
      )}
    >
      <Primitive.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow transition-transform duration-200 data-[state=checked]:translate-x-[18px]" />
    </Primitive.Root>
  )
}
