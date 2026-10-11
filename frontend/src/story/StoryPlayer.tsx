import { ChevronLeft, ChevronRight, MonitorPlay, Pause, Play, X } from 'lucide-react'
import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/cn'
import { formatDate, formatShare } from '@/lib/format'
import { peakWeek } from '@/lib/metrics'
import { useReducedMotion } from '@/lib/motion'
import { useExplorer, type LayerId } from '@/lib/store'
import { useStory } from '@/lib/storyStore'
import { weekDates } from '@/lib/time'
import type { SeasonData, SmokeRunSummary } from '@/lib/types'
import { CHAPTERS, dueCues, storyContext } from './chapters'

const CONTROL =
  'focus-ring text-text-2 inline-flex size-8 cursor-pointer items-center justify-center rounded-full hover:text-white disabled:cursor-not-allowed disabled:opacity-35'
/** The before/after divider sweeps across and back while the "scars stay" chapter plays. */
const WIPE = { from: 6, to: 24, low: 14, high: 88 }

/** Starts the story. Sits beside the timeline. */
export function StoryButton() {
  const { t } = useTranslation()
  const running = useStory((s) => s.chapter !== null)
  const start = useStory((s) => s.start)
  if (running) return null
  return (
    <button
      type="button"
      onClick={start}
      title={t('story.play')}
      aria-label={t('story.play')}
      data-testid="story-button"
      className="panel focus-ring text-text hover:border-ember/60 inline-flex shrink-0 cursor-pointer items-center gap-2 px-3.5 text-sm font-medium transition-colors duration-200"
    >
      <Play size={15} className="text-ember-2" aria-hidden />
      <span className="max-xl:sr-only">{t('story.short')}</span>
    </button>
  )
}

/**
 * Plays the five chapters (brief §13.1) by driving the Explorer's own controls, and shows the
 * caption for each. With reduced motion nothing moves by itself: each chapter is a still scene
 * and the viewer steps through.
 */
export function StoryPlayer(props: { data: SeasonData; runs: SmokeRunSummary[] }) {
  const { data, runs } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const reduced = useReducedMotion()
  const chapter = useStory((s) => s.chapter)
  const paused = useStory((s) => s.paused)
  const presenting = useStory((s) => s.presenting)
  const bar = useRef<HTMLDivElement>(null)

  const context = useMemo(() => {
    const names = data.summary.districts.map((d) => d.district)
    const week = peakWeek(data.summary, names)
    return week === null ? null : storyContext(data, week, weekDates(week), runs, reduced)
  }, [data, runs, reduced])

  // What the viewer had on screen comes back when the story ends.
  const before = useRef<{ layers: Record<LayerId, boolean>; scope: 'week' | 'season' } | null>(null)
  const running = chapter !== null
  useEffect(() => {
    if (!running) return
    const explorer = useExplorer.getState()
    before.current = { layers: explorer.layers, scope: explorer.scope }
    return () => {
      const now = useExplorer.getState()
      now.setPlaying(false)
      now.setSpeed(1)
      now.setStoryEmbers(null)
      now.setImageryWipe(null)
      if (before.current !== null) {
        now.setLayers(before.current.layers)
        now.setScope(before.current.scope)
      }
    }
  }, [running])

  // One loop per chapter: fire its cues as they fall due, move the progress bar and the
  // before/after divider, and go on to the next chapter when the time is up.
  useEffect(() => {
    if (chapter === null || context === null) return
    const current = CHAPTERS[chapter]
    for (const cue of dueCues(current, -1, 0)) cue.run(context)
    let elapsed = 0
    let last = performance.now()
    let resume = false
    let frame = 0
    const tick = (now: number) => {
      const dt = Math.min(0.25, (now - last) / 1000)
      last = now
      const story = useStory.getState()
      const explorer = useExplorer.getState()
      if (story.paused) {
        if (explorer.playing) {
          resume = true
          explorer.setPlaying(false)
        }
      } else if (!reduced) {
        if (resume) {
          resume = false
          explorer.setPlaying(true)
        }
        const earlier = elapsed
        elapsed += dt
        for (const cue of dueCues(current, earlier, elapsed)) cue.run(context)
        if (current.id === 'scars' && elapsed >= WIPE.from && elapsed <= WIPE.to) {
          const phase = ((elapsed - WIPE.from) / (WIPE.to - WIPE.from)) * Math.PI * 3
          explorer.setImageryWipe(WIPE.low + (WIPE.high - WIPE.low) * (0.5 + 0.5 * Math.cos(phase)))
        }
        if (bar.current) bar.current.style.width = `${Math.min(100, (elapsed / current.seconds) * 100)}%`
        if (elapsed >= current.seconds) {
          if (chapter < CHAPTERS.length - 1) story.go(chapter + 1)
          else story.stop()
          return
        }
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [chapter, context, reduced])

  // P toggles presentation mode; Escape leaves the story.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement && event.target.closest('input, textarea, [contenteditable]')
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key.toLowerCase() === 'p') useStory.getState().togglePresenting()
      else if (event.key === 'Escape' && useStory.getState().chapter !== null) useStory.getState().stop()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (chapter === null || context === null) return null
  const id = CHAPTERS[chapter].id
  const key = `c${chapter + 1}` as 'c1' | 'c2' | 'c3' | 'c4' | 'c5'
  const note = {
    pass: () => t('story.c1.note', { date: formatDate(context.day, language, true) }),
    after: () => t('story.c2.note'),
    scars: () =>
      context.village === null
        ? ''
        : t('story.c3.note', { village: context.village.name, district: context.village.district }),
    missed: () => t('story.c4.note', { share: formatShare(data.summary.totals.unrecorded_share) }),
    smoke: () =>
      context.run === null
        ? t('story.noRun')
        : t('story.c5.note', { date: formatDate(context.run.start * 1000, language, true) }),
  }[id]()
  const story = useStory.getState()

  return (
    <section
      className={cn(
        'panel pointer-events-auto mx-auto flex w-full flex-col gap-2 px-5 py-4',
        presenting ? 'max-w-5xl' : 'max-w-3xl',
      )}
      aria-label={t('story.play')}
      data-testid="story"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0" aria-live="polite">
          <p
            className={cn(
              'font-display text-text leading-tight font-semibold text-balance',
              presenting ? 'text-4xl' : 'text-xl',
            )}
            data-testid="story-caption"
          >
            {t(`story.${key}.title`)}
          </p>
          <p className={cn('text-text-2 mt-1.5 leading-snug', presenting ? 'text-lg' : 'text-xs')}>
            {id === 'after' && (
              <span className="border-ember/50 text-ember-2 mr-1.5 rounded-full border px-1.5 py-px text-[0.8em] font-medium tracking-wide uppercase">
                {t('hero.illustration')}
              </span>
            )}
            {note}
          </p>
        </div>
        {!presenting && (
          <div className="flex shrink-0 items-center gap-0.5">
            <button
              type="button"
              className={CONTROL}
              disabled={chapter === 0}
              onClick={() => story.go(chapter - 1)}
              aria-label={t('story.previous')}
              title={t('story.previous')}
            >
              <ChevronLeft size={17} aria-hidden />
            </button>
            {!reduced && (
              <button
                type="button"
                className={CONTROL}
                onClick={() => story.setPaused(!paused)}
                aria-label={paused ? t('story.resume') : t('story.pause')}
                title={paused ? t('story.resume') : t('story.pause')}
              >
                {paused ? <Play size={15} aria-hidden /> : <Pause size={15} aria-hidden />}
              </button>
            )}
            <button
              type="button"
              className={CONTROL}
              onClick={() => (chapter < CHAPTERS.length - 1 ? story.go(chapter + 1) : story.stop())}
              aria-label={t('story.next')}
              title={t('story.next')}
            >
              <ChevronRight size={17} aria-hidden />
            </button>
            <button
              type="button"
              className={CONTROL}
              onClick={story.togglePresenting}
              aria-label={t('story.present')}
              title={t('story.present')}
            >
              <MonitorPlay size={15} aria-hidden />
            </button>
            <button
              type="button"
              className={CONTROL}
              onClick={story.stop}
              aria-label={t('story.close')}
              title={t('story.close')}
            >
              <X size={16} aria-hidden />
            </button>
          </div>
        )}
      </div>
      <div className="flex items-center gap-3">
        <ol className="flex flex-1 gap-1" aria-label={t('story.chapterOf', { n: chapter + 1, total: CHAPTERS.length })}>
          {CHAPTERS.map((item, index) => (
            <li key={item.id} className="h-1 flex-1 overflow-hidden rounded-full bg-white/12">
              <div
                ref={index === chapter ? bar : undefined}
                className="bg-ember h-full"
                style={{ width: index < chapter ? '100%' : index === chapter && reduced ? '100%' : '0%' }}
              />
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
