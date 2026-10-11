import { useState, type ReactNode } from 'react'
import { Drawer } from 'vaul'
import { cn } from '@/lib/cn'

export interface SheetTab {
  id: string
  label: string
  content: ReactNode
}

/** Collapsed: the handle, the bar and the tabs. Then half the screen, then nearly all of it. */
const SNAPS = ['176px', 0.55, 0.92]

/**
 * The phone layout's bottom sheet (brief §12.2): always present, dragged up to read a panel.
 * `bar` stays visible when the sheet is collapsed; it holds the timeline.
 */
export function PhoneSheet(props: { title: string; bar: ReactNode; tabs: SheetTab[] }) {
  const [snap, setSnap] = useState<number | string | null>(SNAPS[0])
  const [tab, setTab] = useState(props.tabs[0]?.id)
  const active = props.tabs.find((item) => item.id === tab) ?? props.tabs[0]
  return (
    <Drawer.Root
      open
      modal={false}
      dismissible={false}
      snapPoints={SNAPS}
      activeSnapPoint={snap}
      setActiveSnapPoint={setSnap}
    >
      <Drawer.Portal>
        <Drawer.Content
          className="panel fixed inset-x-0 bottom-0 z-20 flex h-[92dvh] flex-col rounded-b-none outline-none [--panel-left:100%] [--panel-right:100%]"
          data-testid="phone-sheet"
        >
          <Drawer.Handle className="mt-2 mb-1 bg-white/30" />
          <Drawer.Title className="sr-only">{props.title}</Drawer.Title>
          <div className="px-2">{props.bar}</div>
          <div className="flex gap-1 px-3 pt-2 pb-1" role="tablist" aria-label={props.title}>
            {props.tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={item.id === active?.id}
                onClick={() => {
                  setTab(item.id)
                  // Choosing a tab from the collapsed sheet opens it far enough to read.
                  if (snap === SNAPS[0]) setSnap(SNAPS[1])
                }}
                className={cn(
                  'focus-ring flex-1 cursor-pointer rounded-lg px-2 py-2 text-xs font-medium',
                  item.id === active?.id ? 'text-text bg-white/12' : 'text-text-2',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          {/* The panels keep their own content; inside the sheet they lose their glass frame. */}
          <div
            role="tabpanel"
            className="flex min-h-0 flex-1 flex-col overflow-y-auto [&>section]:max-h-none [&>section]:w-full [&>section]:border-0 [&>section]:bg-transparent [&>section]:shadow-none [&>section]:backdrop-filter-none [&>section]:before:hidden"
          >
            {active?.content}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}
