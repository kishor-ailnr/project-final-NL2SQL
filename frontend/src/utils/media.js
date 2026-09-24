/**
 * Utility helpers for safely playing and pausing HTMLMediaElements (Audio / Video),
 * guarding against "AbortError: The play() request was interrupted by a call to pause()".
 */

/**
 * Safely plays an HTMLMediaElement (audio or video).
 * Catches and ignores AbortError if pause() is called before the play() promise resolves.
 *
 * @param {HTMLMediaElement | null} element - The audio or video element
 * @returns {Promise<void>}
 */
export async function safePlay(element) {
  if (!element || typeof element.play !== 'function') return;

  try {
    const playPromise = element.play();
    if (playPromise !== undefined && typeof playPromise.then === 'function') {
      await playPromise;
    }
  } catch (error) {
    if (
      error.name === 'AbortError' ||
      error.message?.includes('interrupted by a call to pause')
    ) {
      // Expected browser behavior when paused before play finished; safe to ignore.
      return;
    }
    console.warn('Playback error:', error);
  }
}

/**
 * Safely pauses an HTMLMediaElement only if it is currently playing.
 *
 * @param {HTMLMediaElement | null} element - The audio or video element
 */
export function safePause(element) {
  if (!element || typeof element.pause !== 'function') return;

  if (!element.paused) {
    element.pause();
  }
}
