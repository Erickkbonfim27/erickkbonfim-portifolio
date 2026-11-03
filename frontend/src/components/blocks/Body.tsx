import type { MouseEvent } from "react";
import type { Block, Segment } from "../../api/types";
import { navigate } from "../../lib/router";
import { Diagram } from "./Diagram";
import { Gallery } from "./Gallery";
import { Cases, Facts, Logos, Metrics, Quote } from "./Simple";
import { StreetMap } from "./StreetMap";
import { Timeline } from "./Timeline";

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "facts":
      return <Facts data={block.data} />;
    case "metrics":
      return <Metrics data={block.data} />;
    case "gallery":
      return <Gallery data={block.data} />;
    case "timeline":
      return <Timeline data={block.data} />;
    case "diagram":
      return <Diagram data={block.data} />;
    case "logos":
      return <Logos data={block.data} />;
    case "cases":
      return <Cases data={block.data} />;
    case "quote":
      return <Quote data={block.data} />;
    case "map":
      return <StreetMap data={block.data} />;
    default:
      return null; // a kind this build doesn't know yet: skip it rather than break the page
  }
}

/** Links to other pages of the site ("/work/vizzion") change page without a reload. */
function followInternal(event: MouseEvent<HTMLDivElement>) {
  const anchor = (event.target as Element).closest("a");
  const href = anchor?.getAttribute("href");
  if (!href?.startsWith("/") || href.startsWith("//") || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(href);
}

/** A case study or article body: server-rendered HTML runs between structured blocks. */
export function Body({ segments, fallbackHtml }: { segments: Segment[] | undefined; fallbackHtml: string }) {
  const parts: Segment[] = segments?.length ? segments : fallbackHtml ? [{ type: "html", html: fallbackHtml }] : [];
  if (parts.length === 0) return null;
  return (
    <div className="cflow">
      {parts.map((segment, index) =>
        segment.type === "html" ? (
          // Rendered and sanitized by the API from an allow-list of nodes.
          <div key={index} className="prose flow-prose" onClick={followInternal} dangerouslySetInnerHTML={{ __html: segment.html }} />
        ) : (
          <div key={index} className={`flow-block fb-${segment.kind}`}>
            <BlockView block={segment} />
          </div>
        ),
      )}
    </div>
  );
}
