import type { BlockData } from "../../api/types";
import { useI18n } from "../../i18n";
import { useActiveIndex, useInView } from "../../lib/useInView";
import { ArrowUpRight } from "../Icons";

type Item = BlockData["timeline"]["items"][number];

/** A road-book "tulip": where you arrive (dot), the way in (stem) and the turn out
 * (arrow). Each stage turns a little differently, the way a rally route does. */
function Tulip({ index }: { index: number }) {
  const angles = [-35, 40, 0, -60, 25, 70, -15, 50];
  const angle = angles[index % angles.length] ?? 0;
  const rad = (angle * Math.PI) / 180;
  const [x, y] = [32 + Math.sin(rad) * 22, 30 - Math.cos(rad) * 22];
  return (
    <svg className="tulip" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="30" r="20" className="tulip-ring" />
      <path d="M32 58 L32 30" className="tulip-in" />
      <path d={`M32 30 L${x.toFixed(1)} ${y.toFixed(1)}`} className="tulip-out" />
      <circle cx={x} cy={y} r="3.4" className="tulip-head" />
      <circle cx="32" cy="30" r="3" className="tulip-dot" />
    </svg>
  );
}

function Notes({ item }: { item: Item }) {
  return (
    <div className="rb-notes">
      <h3>{item.title}</h3>
      {item.place && <span className="rb-place mono">{item.place}</span>}
      {item.text && <p>{item.text}</p>}
      {item.link && (
        <a className="tlink" href={item.link.url} target="_blank" rel="noopener noreferrer">
          {item.link.label}
          <ArrowUpRight size={13} />
        </a>
      )}
    </div>
  );
}

function Roadbook({ data }: { data: BlockData["timeline"] }) {
  const { t } = useI18n();
  const [active, bind] = useActiveIndex(data.items.length);
  const progress = data.items.length > 1 ? active / (data.items.length - 1) : 1;
  return (
    <section className="blk-roadbook card dark" aria-label={data.title}>
      {data.title && <h3 className="rb-title label mono">{data.title}</h3>}
      <div className="rb-track" aria-hidden="true">
        <span className="rb-fill" style={{ transform: `scaleY(${progress})` }} />
      </div>
      <ol className="rb-list">
        {data.items.map((item, index) => (
          <li key={`${item.when}-${item.title}`} {...bind(index)} className={`rb-row${index <= active ? " on" : ""}`}>
            <div className="rb-stage mono">
              <span className="rb-ss">
                {item.tag ?? `${t.blocks.stage}${index + 1}`}
              </span>
              <span className="rb-when">{item.when}</span>
            </div>
            <Tulip index={index} />
            <Notes item={item} />
            {item.image && <img className="rb-photo" src={item.image.src} alt={item.image.alt} loading="lazy" />}
          </li>
        ))}
      </ol>
    </section>
  );
}

function List({ data }: { data: BlockData["timeline"] }) {
  const [ref, seen] = useInView<HTMLOListElement>(0.1);
  return (
    <section className="blk-timeline" aria-label={data.title}>
      {data.title && <h3 className="label mono">{data.title}</h3>}
      <ol ref={ref} className={`tl-list${seen ? " in" : ""}`}>
        {data.items.map((item, index) => (
          <li key={`${item.when}-${item.title}`} style={{ transitionDelay: `${Math.min(index, 10) * 70}ms` }}>
            <span className="tl-when mono">{item.when}</span>
            <div className="tl-body">
              {item.tag && <span className="tag mono">{item.tag}</span>}
              <Notes item={item} />
              {item.image && <img className="tl-photo" src={item.image.src} alt={item.image.alt} loading="lazy" />}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Timeline({ data }: { data: BlockData["timeline"] }) {
  return data.style === "roadbook" ? <Roadbook data={data} /> : <List data={data} />;
}
