import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { Toaster } from 'sonner'
import { Delhi } from './app/Delhi'
import { Explorer } from './app/Explorer'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/map" element={<Explorer />} />
        <Route path="/delhi" element={<Delhi />} />
        {/* The globe hero arrives in a later phase; until then the app opens on the map. */}
        <Route path="*" element={<Navigate to="/map" replace />} />
      </Routes>
      <Toaster theme="dark" position="bottom-center" />
    </BrowserRouter>
  )
}
