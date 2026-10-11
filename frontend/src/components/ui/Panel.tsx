import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/** A floating glass panel with a display-font heading. */
export function Panel(props: { title: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('panel flex min-h-0 flex-col', props.className)} aria-label={props.title}>
      <header className="flex items-center justify-between gap-2 px-4 pt-3.5 pb-2">
        <h2 className="font-display text-text text-sm font-semibold tracking-[0.14em] uppercase">{props.title}</h2>
        {props.actions}
      </header>
      {props.children}
    </section>
  )
}

export function SectionLabel(props: { children: ReactNode }) {
  return <h3 className="text-text-2 mb-1.5 text-[11px] font-medium tracking-[0.12em] uppercase">{props.children}</h3>
}
