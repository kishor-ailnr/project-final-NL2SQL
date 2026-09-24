import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Intercept and safely handle HTMLMediaElement play() interruptions (AbortError)
// This occurs when play() and pause() are called in rapid succession during React re-renders or unmounts.
if (typeof window !== 'undefined') {
  if (typeof HTMLMediaElement !== 'undefined') {
    const originalPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...args) {
      const playPromise = originalPlay.apply(this, args);
      if (playPromise !== undefined && typeof playPromise.catch === 'function') {
        return playPromise.catch((error) => {
          if (
            error.name === 'AbortError' ||
            error.message?.includes('interrupted by a call to pause')
          ) {
            // Expected browser behavior when pause() is called before play() finishes; safely ignore.
            return;
          }
          throw error;
        });
      }
      return playPromise;
    };
  }

  // Prevent uncaught promise rejection from logging AbortError to console
  window.addEventListener('unhandledrejection', (event) => {
    if (
      event.reason?.name === 'AbortError' ||
      event.reason?.message?.includes('interrupted by a call to pause')
    ) {
      event.preventDefault();
    }
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
