const stateTokens = {
  idle: '--muted', listening: '--accent', thinking: '--activity',
  'agent-working': '--activity', speaking: '--accent',
  'approval-needed': '--warning', warning: '--warning', 'outcome-unknown': '--unknown'
};

/** Bounded 3D lattice projected with Canvas2D; no WebGL dependency. */
export class CommandCore {
  constructor(canvas, {reduced = false, fixed = false, onMetrics = () => {}} = {}) {
    this.canvas = canvas;
    try { this.ctx = canvas.getContext('2d'); } catch { this.ctx = null; }
    this.reduced = reduced;
    this.fixed = fixed;
    this.state = 'idle';
    this.phase = 0;
    this.visible = true;
    this.disposed = false;
    this.frame = null;
    this.drops = 0;
    this.samples = innerWidth < 760 ? 24 : 36;
    this.onMetrics = onMetrics;
    const theme = getComputedStyle(document.documentElement);
    this.colors = Object.fromEntries(Object.entries(stateTokens).map(([state, token]) =>
      [state, theme.getPropertyValue(token).trim()]));
    this.visibility = () => document.hidden ? this.pause() : this.resume();
    document.addEventListener('visibilitychange', this.visibility);
    this.observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
      this.visible = entries[0].isIntersecting;
      this.visible ? this.resume() : this.pause();
    }) : null;
    this.observer?.observe(canvas);
    this.resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(() => this.draw()) : null;
    this.resizeObserver?.observe(canvas);
    if (!this.ctx) {
      canvas.hidden = true;
      canvas.parentElement.classList.add('core-fallback');
      return;
    }
    this.draw();
    this.resume();
  }

  setState(state) { this.state = stateTokens[state] ? state : 'idle'; this.draw(); }
  setReduced(value) { this.reduced = value; this.pause(); this.draw(); this.resume(); }
  pause() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.last = null;
  }
  resume() {
    if (this.frame !== null || this.disposed || !this.ctx || this.reduced || this.fixed || !this.visible || document.hidden) return;
    this.frame = requestAnimationFrame(time => this.tick(time));
  }
  tick(time) {
    this.frame = null;
    if (this.last && time - this.last > 42 && ++this.drops > 12) this.samples = 24;
    const delta = this.last ? Math.min(.04, (time - this.last) / 1000) : 0;
    this.last = time;
    this.phase += delta * (this.state === 'thinking' ? .24 : this.state === 'outcome-unknown' ? .025 : .075);
    this.draw();
    this.onMetrics({drops: this.drops, samples: this.samples});
    this.resume();
  }

  draw() {
    if (!this.ctx) return;
    const size = this.canvas.getBoundingClientRect();
    const width = size.width || 440, height = size.height || 440;
    const dpr = Math.min(2, devicePixelRatio || 1);
    if (this.canvas.width !== Math.round(width * dpr)) this.canvas.width = Math.round(width * dpr);
    if (this.canvas.height !== Math.round(height * dpr)) this.canvas.height = Math.round(height * dpr);
    const c = this.ctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, width, height);
    const cx = width / 2, cy = height / 2, radius = Math.min(width, height) * .31;
    const color = this.colors[this.state];
    const project = (latitude, longitude) => {
      const x = Math.cos(latitude) * Math.cos(longitude);
      const y = Math.sin(latitude), z = Math.cos(latitude) * Math.sin(longitude);
      const rotation = this.phase + .42;
      const horizontal = x * Math.cos(rotation) + z * Math.sin(rotation);
      const depth = -x * Math.sin(rotation) + z * Math.cos(rotation);
      const vertical = y * Math.cos(.38) - depth * Math.sin(.38);
      const cameraDepth = y * Math.sin(.38) + depth * Math.cos(.38);
      const scale = 1 / (1 - cameraDepth * .15);
      return [cx + horizontal * radius * scale, cy + vertical * radius * scale];
    };
    c.lineWidth = .7;
    c.strokeStyle = color;
    for (let latitude = -6; latitude <= 6; latitude++) {
      c.beginPath();
      for (let sample = 0; sample <= this.samples; sample++) {
        const point = project(latitude * Math.PI / 14, sample * 2 * Math.PI / this.samples);
        sample ? c.lineTo(...point) : c.moveTo(...point);
      }
      c.globalAlpha = .18 + Math.abs(latitude) / 50;
      c.stroke();
    }
    for (let longitude = 0; longitude < 18; longitude++) {
      c.beginPath();
      for (let sample = 0; sample <= this.samples; sample++) {
        const point = project(-Math.PI / 2 + sample * Math.PI / this.samples, longitude * 2 * Math.PI / 18);
        sample ? c.lineTo(...point) : c.moveTo(...point);
      }
      c.globalAlpha = .21;
      c.stroke();
    }
    c.lineWidth = 1.1;
    for (let orbit = 0; orbit < 3; orbit++) {
      c.beginPath();
      const angle = orbit * 1.04 + this.phase * .4;
      for (let sample = 0; sample <= 100; sample++) {
        const t = sample * Math.PI * 2 / 100;
        const x = Math.cos(t) * radius * 1.36, y = Math.sin(t) * radius * .35;
        // State feedback only: browser recognition does not expose amplitude.
        const wave = ['speaking', 'listening'].includes(this.state) ? Math.sin(t * 9 + this.phase * 45) * radius * .025 : 0;
        const point = [cx + x * Math.cos(angle) - (y + wave) * Math.sin(angle),
          cy + x * Math.sin(angle) + (y + wave) * Math.cos(angle)];
        sample ? c.lineTo(...point) : c.moveTo(...point);
      }
      c.globalAlpha = orbit === 0 ? .64 : .26;
      c.stroke();
    }
    c.globalAlpha = .9;
    c.fillStyle = color;
    for (let pointIndex = 0; pointIndex < 7; pointIndex++) {
      const point = project(.3 * Math.sin(pointIndex), this.phase * 2 + pointIndex * .86);
      c.beginPath();
      c.arc(...point, 1.4, 0, Math.PI * 2);
      c.fill();
    }
    c.globalAlpha = 1;
  }

  dispose() {
    this.disposed = true;
    this.pause();
    this.observer?.disconnect();
    this.resizeObserver?.disconnect();
    document.removeEventListener('visibilitychange', this.visibility);
  }
}
