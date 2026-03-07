/**
 * Component: App
 * Purpose: Outermost component wrapper.
 * WHY: Sets up context providers and routing boundaries. Real routing defined in Epoch 5.
 */
import React from 'react';

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-background bg-mesh text-foreground font-sans flex items-center justify-center">
      <div className="glass-panel p-12 rounded-2xl max-w-lg text-center">
        <h1 className="text-4xl font-bold tracking-tight text-gradient mb-4">LLMWatch Engine</h1>
        <p className="text-muted-foreground">Frontend scaffolded successfully. Routes injecting soon.</p>
      </div>
    </div>
  );
};

export default App;
