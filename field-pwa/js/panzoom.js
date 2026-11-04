// 이미지 드래그 / 핀치 줌 / 휠 줌 / 더블탭 줌
export class PanZoom {
  constructor(viewport, img, { initial, onChange } = {}) {
    this.vp = viewport;
    this.img = img;
    this.onChange = onChange;
    this.x = 0;
    this.y = 0;
    this.scale = 1;
    this.fitScale = 1;
    this.pointers = new Map();
    this.pinch = null;
    this.lastTap = 0;
    this.initial = initial || null;
    this._bind();
    if (img.complete && img.naturalWidth) this.fit();
    else img.addEventListener("load", () => this.fit(), { once: true });
    this._ro = new ResizeObserver(() => {
      if (img.naturalWidth) this._clamp(), this._apply();
    });
    this._ro.observe(viewport);
  }

  destroy() {
    this._ro?.disconnect();
  }

  get minScale() {
    return this.fitScale * 0.7;
  }
  get maxScale() {
    return Math.max(this.fitScale * 12, 1.5);
  }

  fit() {
    const vw = this.vp.clientWidth;
    const vh = this.vp.clientHeight;
    const iw = this.img.naturalWidth;
    const ih = this.img.naturalHeight;
    if (!vw || !vh || !iw || !ih) return;
    this.fitScale = Math.min(vw / iw, vh / ih);
    if (this.initial && this.initial.scale) {
      this.scale = this.initial.scale;
      this.x = this.initial.x;
      this.y = this.initial.y;
    } else {
      this.scale = this.fitScale;
      this.x = (vw - iw * this.scale) / 2;
      this.y = (vh - ih * this.scale) / 2;
    }
    this.initial = null;
    this._clamp();
    this._apply();
  }

  reset() {
    this.initial = null;
    this.fit();
  }

  zoomBy(factor, cx, cy) {
    const vw = this.vp.clientWidth;
    const vh = this.vp.clientHeight;
    const px = cx ?? vw / 2;
    const py = cy ?? vh / 2;
    const next = Math.min(this.maxScale, Math.max(this.minScale, this.scale * factor));
    const k = next / this.scale;
    this.x = px - (px - this.x) * k;
    this.y = py - (py - this.y) * k;
    this.scale = next;
    this._clamp();
    this._apply();
  }

  _clamp() {
    const vw = this.vp.clientWidth;
    const vh = this.vp.clientHeight;
    const w = this.img.naturalWidth * this.scale;
    const h = this.img.naturalHeight * this.scale;
    const margin = 80; // 이미지가 화면 밖으로 완전히 사라지지 않게
    this.x = Math.min(vw - margin, Math.max(margin - w, this.x));
    this.y = Math.min(vh - margin, Math.max(margin - h, this.y));
  }

  _apply() {
    this.img.style.transform = `translate(${this.x}px, ${this.y}px) scale(${this.scale})`;
    this.onChange?.({ x: this.x, y: this.y, scale: this.scale });
  }

  _local(e) {
    const r = this.vp.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  _bind() {
    const vp = this.vp;
    vp.addEventListener("pointerdown", (e) => {
      if (e.target.closest?.(".hall-pin")) return; // 홀 표시는 눌러서 열어야 하므로 드래그로 가로채지 않는다
      vp.setPointerCapture?.(e.pointerId);
      this.pointers.set(e.pointerId, this._local(e));
      if (this.pointers.size === 2) this._startPinch();
      if (this.pointers.size === 1) {
        const now = Date.now();
        const p = this._local(e);
        if (now - this.lastTap < 300) {
          this.zoomBy(2, p.x, p.y);
          this.lastTap = 0;
        } else {
          this.lastTap = now;
        }
      }
    });

    vp.addEventListener("pointermove", (e) => {
      if (!this.pointers.has(e.pointerId)) return;
      const prev = this.pointers.get(e.pointerId);
      const cur = this._local(e);
      this.pointers.set(e.pointerId, cur);
      if (this.pointers.size === 1) {
        this.x += cur.x - prev.x;
        this.y += cur.y - prev.y;
        this._clamp();
        this._apply();
      } else if (this.pointers.size === 2 && this.pinch) {
        const [a, b] = [...this.pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
        const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        const target = Math.min(this.maxScale, Math.max(this.minScale, this.pinch.scale * (dist / this.pinch.dist)));
        const k = target / this.scale;
        this.x = mid.x - (mid.x - this.x) * k + (mid.x - this.pinch.mid.x);
        this.y = mid.y - (mid.y - this.y) * k + (mid.y - this.pinch.mid.y);
        this.scale = target;
        this.pinch.mid = mid;
        this._clamp();
        this._apply();
      }
    });

    const end = (e) => {
      this.pointers.delete(e.pointerId);
      this.pinch = null;
      if (this.pointers.size === 2) this._startPinch();
    };
    vp.addEventListener("pointerup", end);
    vp.addEventListener("pointercancel", end);

    vp.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const p = this._local(e);
        this.zoomBy(Math.exp(-e.deltaY * 0.0015), p.x, p.y);
      },
      { passive: false },
    );
  }

  _startPinch() {
    const [a, b] = [...this.pointers.values()];
    this.pinch = {
      dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
      mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      scale: this.scale,
    };
  }
}
