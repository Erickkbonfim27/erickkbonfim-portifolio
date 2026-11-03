import { useEffect, useRef, useState } from "react";
import type { BlockData } from "../../api/types";
import { useI18n } from "../../i18n";
import { useInView } from "../../lib/useInView";

type Items = BlockData["gallery"]["items"];

function Lightbox({ items, index, onMove, onClose }: { items: Items; index: number; onMove: (i: number) => void; onClose: () => void }) {
  const { t } = useI18n();
  const close = useRef<HTMLButtonElement>(null);
  const item = items[index];
  const many = items.length > 1;
  const go = (step: number) => onMove((index + step + items.length) % items.length);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    return () => previous?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (many && event.key === "ArrowRight") onMove((index + 1) % items.length);
      if (many && event.key === "ArrowLeft") onMove((index - 1 + items.length) % items.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, items.length, many, onClose, onMove]);

  if (!item) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={item.alt} onClick={onClose}>
      <figure onClick={(event) => event.stopPropagation()}>
        <img src={item.src} alt={item.alt} />
        <figcaption>
          <span>{item.caption ?? item.alt}</span>
          {many && (
            <span className="mono lb-count">
              {index + 1} / {items.length}
            </span>
          )}
        </figcaption>
      </figure>
      <div className="lb-controls" onClick={(event) => event.stopPropagation()}>
        {many && (
          <button type="button" className="arrowbtn" aria-label={t.blocks.previous} onClick={() => go(-1)}>
            ←
          </button>
        )}
        {many && (
          <button type="button" className="arrowbtn" aria-label={t.blocks.next} onClick={() => go(1)}>
            →
          </button>
        )}
        <button ref={close} type="button" className="pillbtn pill-light sm lb-close" onClick={onClose}>
          {t.blocks.close}
        </button>
      </div>
    </div>
  );
}

export function Gallery({ data }: { data: BlockData["gallery"] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<number | null>(null);
  const [ref, seen] = useInView<HTMLDivElement>(0.1);
  const layout = data.layout ?? "grid";
  return (
    <div ref={ref} className={`blk-gallery g-${layout}${seen ? " in" : ""}`}>
      {data.items.map((item, index) => (
        <figure key={item.src} className={item.wide ? "wide" : undefined} style={{ transitionDelay: `${Math.min(index, 8) * 60}ms` }}>
          <button type="button" className="g-open" onClick={() => setOpen(index)} aria-label={t.blocks.open(item.alt)}>
            <img src={item.src} alt={item.alt} loading="lazy" />
          </button>
          {item.caption && <figcaption>{item.caption}</figcaption>}
        </figure>
      ))}
      {open !== null && <Lightbox items={data.items} index={open} onMove={setOpen} onClose={() => setOpen(null)} />}
    </div>
  );
}
