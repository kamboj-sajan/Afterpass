export default function App() {
  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">AfterPass</h1>
      <p className="text-text-2 max-w-md">
        The satellites look at 1:30 PM. The fields burn after.
      </p>
      <div className="flex gap-3 text-sm">
        <span className="border-hairline rounded-full border px-3 py-1 text-official">
          ● Official detections
        </span>
        <span className="border-hairline rounded-full border px-3 py-1 text-ember">
          ● Burn scars found
        </span>
      </div>
      <p className="text-text-2 text-xs">Scaffold — the map arrives in Phase 3.</p>
    </main>
  )
}
