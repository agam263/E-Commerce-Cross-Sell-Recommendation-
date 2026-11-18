import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import ProductExplorer from './pages/ProductExplorer'
import RuleExplorer from './pages/RuleExplorer'
import RevenueSimulator from './pages/RevenueSimulator'
import ModelInfo from './pages/ModelInfo'
import Help from './pages/Help'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/products" element={<ProductExplorer />} />
        <Route path="/rules" element={<RuleExplorer />} />
        <Route path="/simulator" element={<RevenueSimulator />} />
        <Route path="/model" element={<ModelInfo />} />
        <Route path="/help" element={<Help />} />
        <Route
          path="*"
          element={
            <div className="card card-pad">
              <p className="font-semibold">Page not found</p>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Use the navigation on the left.
              </p>
            </div>
          }
        />
      </Routes>
    </Layout>
  )
}
