import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import MandateDetails from './pages/MandateDetails'
import './styles/App.css'

function App() {
  return (
    <Router>
      <div className="App">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/mandate/:id" element={<MandateDetails />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
