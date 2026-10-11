/**
 * Accessibility check of every screen with axe-core, at desktop and phone size.
 * Needs `make serve-data` and `make web`. Usage: node scripts/axe-check.mjs [appUrl]
 * Exits with 1 if any violation is found, after listing them.
 */
import AxeBuilder from '@axe-core/playwright'
import { chromium } from 'playwright'

const appUrl = process.argv[2] ?? 'http://127.0.0.1:5173'
const SCREENS = [
  { path: '/', ready: 'hero' },
  { path: '/map', ready: 'kpi-value' },
  { path: '/delhi', ready: 'delhi-screen' },
  { path: '/method', ready: 'method-pm25' },
]
const SIZES = [
  { name: 'desktop', viewport: { width: 1440, height: 900 } },
  { name: 'phone', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
]

const browser = await chromium.launch({
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
})
let total = 0
for (const size of SIZES) {
  const context = await browser.newContext(size)
  const page = await context.newPage()
  for (const screen of SCREENS) {
    await page.goto(`${appUrl}${screen.path}`)
    await page.getByTestId(screen.ready).first().waitFor({ timeout: 90_000 })
    await page.waitForTimeout(2500)
    // The map canvas and the basemap's own attribution control are outside what the app styles.
    const results = await new AxeBuilder({ page }).exclude('canvas').exclude('.maplibregl-ctrl-attrib').analyze()
    total += results.violations.length
    console.log(
      `${size.name} ${screen.path}: ${results.violations.length} violation(s), ${results.passes.length} checks passed`,
    )
    for (const violation of results.violations) {
      console.log(`  - [${violation.impact}] ${violation.id}: ${violation.help} (${violation.nodes.length} element(s))`)
      for (const node of violation.nodes.slice(0, 3)) console.log(`      ${node.target.join(' ')}`)
    }
  }
  await context.close()
}
await browser.close()
console.log(total === 0 ? 'No accessibility violations found by axe.' : `${total} violation(s) in total.`)
process.exit(total === 0 ? 0 : 1)
