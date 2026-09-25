import { useState, useRef, useEffect } from 'react';

// Browser-safe check for Web Speech API
const SpeechRecognition =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

export default function VoiceButton({
  onRecordingComplete,
  onTranscript,
  disabled = false,
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [isSupported, setIsSupported] = useState(true);

  // Single recognition instance stored in a ref (created once)
  const recognitionRef = useRef(null);
  // Boolean guard ref to track actual recognition lifecycle
  const isListeningRef = useRef(false);

  // Initialize SpeechRecognition once on mount
  useEffect(() => {
    if (!SpeechRecognition) {
      setIsSupported(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false; // Capture full sentence/utterance
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    // Default to en-IN for English and Thanglish voice input
    recognition.lang = 'en-IN';

    recognition.onstart = () => {
      isListeningRef.current = true;
      setIsRecording(true);
      setErrorMessage(null);
    };

    recognition.onresult = (event) => {
      if (event.results && event.results.length > 0) {
        const transcript = event.results[0][0].transcript;
        if (transcript && transcript.trim()) {
          const text = transcript.trim();
          if (onTranscript) onTranscript(text);
          if (onRecordingComplete) onRecordingComplete(text);
        }
      }
    };

    recognition.onerror = (event) => {
      console.warn('SpeechRecognition error:', event.error);
      isListeningRef.current = false;
      setIsRecording(false);

      // Gracefully ignore benign / user-initiated abort or silence
      if (event.error === 'aborted' || event.error === 'no-speech') {
        return;
      }

      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        setErrorMessage('Microphone access denied. Please allow microphone permissions.');
      } else if (event.error === 'network') {
        setErrorMessage('Speech recognition network error. Please try again.');
      } else {
        setErrorMessage(`Voice recognition error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      isListeningRef.current = false;
      setIsRecording(false);
    };

    recognitionRef.current = recognition;

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (e) {
          // ignore
        }
        recognitionRef.current = null;
      }
      isListeningRef.current = false;
    };
  }, []);

  const handleClick = (e) => {
    e.preventDefault();
    if (disabled) return;

    if (!isSupported) {
      setErrorMessage('Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge.');
      return;
    }

    const recognition = recognitionRef.current;
    if (!recognition) return;

    if (isListeningRef.current) {
      // Safely stop existing active session
      try {
        recognition.stop();
      } catch (err) {
        console.warn('SpeechRecognition stop error:', err);
        try {
          recognition.abort();
        } catch (e) {
          // ignore
        }
      }
      isListeningRef.current = false;
      setIsRecording(false);
    } else {
      // Guarded start
      setErrorMessage(null);
      try {
        recognition.lang = 'en-IN';
        recognition.start();
      } catch (err) {
        console.warn('SpeechRecognition start error:', err);
        if (err.name === 'InvalidStateError' || err.message?.includes('already started')) {
          try {
            recognition.abort();
          } catch (e) {
            // ignore
          }
        }
        isListeningRef.current = false;
        setIsRecording(false);
      }
    }
  };

  return (
    <div className="relative inline-flex items-center shrink-0">
      {/* Inline Error Popover */}
      {errorMessage && (
        <div className="absolute bottom-full mb-2 right-0 sm:left-1/2 sm:-translate-x-1/2 w-64 p-2.5 bg-rose-600 text-white text-xs rounded-xl shadow-lg border border-rose-500 z-30 flex items-start justify-between gap-2 animate-fadeIn">
          <div className="flex items-start gap-1.5">
            <svg className="w-4 h-4 shrink-0 mt-0.5 text-rose-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-rose-200 hover:text-white font-bold leading-none"
          >
            &times;
          </button>
        </div>
      )}

      {/* Mic Trigger Button */}
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        title={isRecording ? 'Click to stop listening' : 'Click to speak question'}
        className={`relative w-11 h-11 min-w-[44px] min-h-[44px] rounded-xl sm:rounded-2xl border transition-all duration-200 shrink-0 flex items-center justify-center ${
          isRecording
            ? 'bg-rose-500 hover:bg-rose-600 text-white border-rose-400 ring-4 ring-rose-200 animate-pulse'
            : errorMessage
            ? 'bg-rose-50 border-rose-300 text-rose-600'
            : 'bg-white hover:bg-teal-50/80 text-slate-600 hover:text-teal-700 border-slate-200/80 hover:border-teal-300 shadow-2xs'
        } disabled:opacity-40 disabled:cursor-not-allowed`}
      >
        {isRecording ? (
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-white animate-ping"></span>
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
            </svg>
          </div>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        )}
      </button>
    </div>
  );
}
