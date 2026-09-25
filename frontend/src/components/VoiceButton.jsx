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
  const [lowConfidenceHint, setLowConfidenceHint] = useState(null);
  const [isSupported, setIsSupported] = useState(true);

  // Single recognition instance stored in a ref (created once)
  const recognitionRef = useRef(null);
  // Boolean guard ref to track actual recognition lifecycle
  const isListeningRef = useRef(false);
  // Timeout ref for dismissing low-confidence hint
  const hintTimeoutRef = useRef(null);

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
      setLowConfidenceHint(null);
      if (hintTimeoutRef.current) {
        clearTimeout(hintTimeoutRef.current);
      }
    };

    recognition.onresult = (event) => {
      if (event.results && event.results.length > 0) {
        const resultItem = event.results[0][0];
        const transcript = resultItem.transcript;
        const confidence = typeof resultItem.confidence === 'number' ? resultItem.confidence : 1.0;

        if (transcript && transcript.trim()) {
          const text = transcript.trim();

          // UX Safety Net: Check if recognized transcript has low confidence or appears
          // to be an unclear attempt at Tamil (e.g. very short, single disjointed syllables,
          // or non-coherent fragments produced by en-IN recognition on pure Tamil speech)
          const words = text.toLowerCase().split(/\s+/).filter(Boolean);
          const isSingleShortWord = words.length === 1 && words[0].length <= 5;
          const isLowScore = confidence > 0 && confidence < 0.65;
          const isFragmentedTamilAttempt =
            words.length <= 2 &&
            /^(ah|eh|oh|da|pa|en|illai|inga|enga|nan|nee|oru|enna|avanga|kaatu|kudu)$/i.test(words[0]);

          if (isLowScore || isSingleShortWord || isFragmentedTamilAttempt) {
            setLowConfidenceHint("Didn't catch that clearly? You can also type in Tamil or English.");
            if (hintTimeoutRef.current) {
              clearTimeout(hintTimeoutRef.current);
            }
            hintTimeoutRef.current = setTimeout(() => {
              setLowConfidenceHint(null);
            }, 9000);
          } else {
            setLowConfidenceHint(null);
          }

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
      if (hintTimeoutRef.current) {
        clearTimeout(hintTimeoutRef.current);
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
      setLowConfidenceHint(null);
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
      {/* 2. Small always-visible hint text near the mic button setting correct upfront expectations */}
      <span
        className="hidden md:inline-block text-[11px] text-slate-400 select-none mr-2 max-w-[195px] leading-tight text-right font-normal"
        title="Voice recognition works best with English and Thanglish. For Tamil, typing is more accurate."
      >
      </span>

      {/* 1. Subtle inline safety-net hint below the input when recognition is low-confidence or fragmented */}
      {lowConfidenceHint && (
        <div className="absolute top-full mt-3 right-0 sm:right-auto sm:left-1/2 sm:-translate-x-1/2 w-72 sm:w-max max-w-[90vw] px-3 py-1.5 bg-amber-50/95 border border-amber-200/90 text-amber-900 text-xs rounded-xl shadow-md z-30 flex items-center justify-between gap-2 animate-fadeIn backdrop-blur-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-amber-500 font-medium">💡</span>
            <span className="font-normal">{lowConfidenceHint}</span>
          </div>
          <button
            type="button"
            onClick={() => setLowConfidenceHint(null)}
            className="text-amber-500 hover:text-amber-800 text-sm font-bold leading-none shrink-0 px-1 ml-1"
            title="Dismiss hint"
          >
            &times;
          </button>
        </div>
      )}

      {/* Inline Microphone Error Popover */}
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
        title={isRecording ? 'Click to stop listening' : 'Click to speak question (English or Thanglish)'}
        className={`relative w-10 h-10 min-w-[40px] min-h-[40px] sm:w-11 sm:h-11 sm:min-w-[44px] sm:min-h-[44px] rounded-full border transition-all duration-200 shrink-0 flex items-center justify-center ${
          isRecording
            ? 'bg-rose-500 hover:bg-rose-600 text-white border-rose-400 ring-4 ring-rose-200 animate-pulse'
            : errorMessage
            ? 'bg-rose-50 border-rose-300 text-rose-600'
            : 'bg-white hover:bg-slate-50 text-slate-500 hover:text-teal-700 border-slate-200/90 hover:border-teal-300 shadow-2xs'
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
