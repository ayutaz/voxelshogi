import { useLayoutEffect, useRef, type ReactNode } from 'react';

/** Modal controls follow the visual order and return focus to their opener. */
export function Sheet({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    root.current?.querySelector<HTMLButtonElement>('[data-close]')?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, [open]);
  return <div className="sheet-backdrop" hidden={!open} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={root} className="sheet" role="dialog" aria-modal="true" aria-label={title} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose(); }
      if (event.key !== 'Tab' || event.altKey || event.ctrlKey || event.metaKey) return;
      const controls = Array.from(root.current?.querySelectorAll<HTMLElement>('button, input, select, a[href], summary, [tabindex="0"]') ?? [])
        .filter(element => !element.matches(':disabled') && !element.closest('[hidden]'));
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}>
      <div className="sheet-heading"><h2>{title}</h2><button type="button" data-close onClick={onClose}>閉じる</button></div>
      {children}
    </div>
  </div>;
}
