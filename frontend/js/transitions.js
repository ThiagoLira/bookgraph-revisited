/**
 * transitions.js — Animated position interpolation for focus mode.
 */

function cubicOut(t) {
  const f = t - 1.0;
  return f * f * f + 1.0;
}

export class TransitionManager {
  constructor() {
    this.animationId = null;
    this.isAnimating = false;
  }

  /**
   * Animate authors from current positions to target positions.
   * @param {Array} authors - Author nodes with x, y
   * @param {Map<string, {x, y}>} targetMap - Target positions by node ID
   * @param {Function} onFrame - Called each frame with progress
   * @param {number} duration - Animation duration in ms (default 600)
   * @returns {Promise} Resolves when animation completes
   */
  animatePositions(authors, targetMap, onFrame, duration = 600) {
    // Cancel any running animation
    this.cancel();

    // Capture start positions
    const startPositions = new Map();
    for (const a of authors) {
      startPositions.set(a.id, { x: a.x, y: a.y });
    }

    this.isAnimating = true;

    return new Promise(resolve => {
      const startTime = performance.now();

      const tick = (now) => {
        const elapsed = now - startTime;
        const rawProgress = Math.min(elapsed / duration, 1);
        const progress = cubicOut(rawProgress);

        // Interpolate positions
        for (const a of authors) {
          const target = targetMap.get(a.id);
          const start = startPositions.get(a.id);

          if (target && start) {
            a.x = start.x + (target.x - start.x) * progress;
            a.y = start.y + (target.y - start.y) * progress;

            // Also update fixed positions if they exist
            if (a.fx !== undefined && a.fx !== null) {
              a.fx = a.x;
              a.fy = a.y;
            }
          }
        }

        if (onFrame) onFrame(progress);

        if (rawProgress < 1) {
          this.animationId = requestAnimationFrame(tick);
        } else {
          this.isAnimating = false;
          this.animationId = null;
          resolve();
        }
      };

      this.animationId = requestAnimationFrame(tick);
    });
  }

  cancel() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    this.isAnimating = false;
  }
}
