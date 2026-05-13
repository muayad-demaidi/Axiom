import { useState } from 'react';
import { ProfessionalDashboard } from './components/ProfessionalDashboard';
import { LandingPage } from './components/LandingPage';

export default function App() {
  const [showDashboard, setShowDashboard] = useState(false);

  if (!showDashboard) {
    return <LandingPage onEnter={() => setShowDashboard(true)} />;
  }

  return <ProfessionalDashboard onGoHome={() => setShowDashboard(false)} />;
}
