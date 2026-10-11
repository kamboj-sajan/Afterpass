import { Info } from 'lucide-react'
import { Popover } from 'radix-ui'
import type { ReactNode } from 'react'

/** A small ⓘ button that opens a note, used for sources and credits. */
export function InfoPopover(props: { label: string; children: ReactNode; side?: 'top' | 'left' | 'right' | 'bottom' }) {
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={props.label}
        className="focus-ring text-text-2 inline-flex size-5 cursor-pointer items-center justify-center rounded-full transition-colors hover:text-white"
      >
        <Info size={14} aria-hidden />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side={props.side ?? 'left'}
          sideOffset={8}
          collisionPadding={12}
          className="panel text-text-2 z-50 max-w-72 p-3 text-xs leading-relaxed"
        >
          {props.children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
