import { Command } from 'cmdk'
import { MapPin, Square, Wind } from 'lucide-react'
import { memo, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { districtCentre } from '@/layers/districts'
import { formatHectares } from '@/lib/format'
import { useExplorer } from '@/lib/store'
import type { SeasonData, SmokeLocality } from '@/lib/types'

const ITEM =
  'flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text data-[selected=true]:bg-white/10'
const GROUP =
  '[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:tracking-[0.12em] [&_[cmdk-group-heading]]:text-text-2 [&_[cmdk-group-heading]]:uppercase'

/** ⌘K / Ctrl+K: find a district, village or Delhi locality and fly there. */
export const CommandPalette = memo(function CommandPalette(props: { data: SeasonData; localities: SmokeLocality[] }) {
  const { data, localities } = props
  const { t, i18n } = useTranslation()
  const setSmokeLocality = useExplorer((s) => s.setSmokeLocality)
  const showLayer = useExplorer((s) => s.showLayer)
  const open = useExplorer((s) => s.paletteOpen)
  const setOpen = useExplorer((s) => s.setPaletteOpen)
  const flyTo = useExplorer((s) => s.flyTo)
  const highlightDistrict = useExplorer((s) => s.highlightDistrict)
  const highlightVillage = useExplorer((s) => s.highlightVillage)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen(!useExplorer.getState().paletteOpen)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label={t('palette.title')}
      overlayClassName="fixed inset-0 z-40 bg-black/50"
      contentClassName="panel fixed top-[18vh] left-1/2 z-50 w-[min(560px,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden"
    >
      <Command.Input
        placeholder={t('palette.placeholder')}
        className="border-hairline text-text placeholder:text-text-2 w-full border-b bg-transparent px-4 py-3.5 text-sm outline-none"
      />
      <Command.List className="scroll-thin max-h-[46vh] overflow-y-auto p-1.5">
        <Command.Empty className="text-text-2 px-3 py-6 text-center text-sm">{t('palette.empty')}</Command.Empty>
        <Command.Group heading={t('palette.districts')} className={GROUP}>
          {data.districts.features.map((feature) => (
            <Command.Item
              key={feature.properties.district}
              value={`${feature.properties.district} ${feature.properties.state}`}
              className={ITEM}
              onSelect={() => {
                const [longitude, latitude] = districtCentre(feature)
                highlightDistrict(feature.properties.district)
                flyTo({ longitude, latitude, zoom: 9.2 })
                setOpen(false)
              }}
            >
              <Square size={14} className="text-text-2" aria-hidden />
              <span>{feature.properties.district}</span>
              <span className="text-text-2 ml-auto text-xs">{feature.properties.state}</span>
            </Command.Item>
          ))}
        </Command.Group>
        <Command.Group heading={t('palette.villages')} className={GROUP}>
          {data.villages.items.map((village) => (
            <Command.Item
              key={`${village.district}-${village.id}`}
              value={`${village.name} ${village.district} ${village.id}`}
              className={ITEM}
              onSelect={() => {
                highlightVillage(village.id)
                flyTo({ longitude: village.lon, latitude: village.lat, zoom: 13.2 })
                setOpen(false)
              }}
            >
              <MapPin size={14} className="text-ember" aria-hidden />
              <span className="truncate">{village.name}</span>
              <span className="text-text-2 ml-auto shrink-0 text-xs">
                {village.district} · <span className="tabular">{formatHectares(village.unrecorded_ha)} ha</span>
              </span>
            </Command.Item>
          ))}
        </Command.Group>
        {localities.length > 0 && (
          <Command.Group heading={t('palette.delhi')} className={GROUP}>
            {localities.map((locality) => (
              <Command.Item
                key={locality.id}
                // Both spellings are searchable, whichever language the app is in.
                value={`${locality.name} ${locality.name_hi ?? ''} ${locality.district} ${locality.id}`}
                className={ITEM}
                onSelect={() => {
                  setSmokeLocality(locality.id)
                  showLayer('delhi')
                  flyTo({ longitude: locality.lon, latitude: locality.lat, zoom: 10.5 })
                  setOpen(false)
                }}
              >
                <Wind size={14} className="text-smoke" aria-hidden />
                <span className="truncate">
                  {i18n.language.startsWith('hi') && locality.name_hi ? locality.name_hi : locality.name}
                </span>
                <span className="text-text-2 ml-auto shrink-0 text-xs">{locality.district}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  )
})
