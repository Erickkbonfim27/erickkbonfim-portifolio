import { useEffect, useRef, useState } from "react";

/** True once the element has scrolled into view (and stays true). Without
 * IntersectionObserver (old browsers, tests) everything counts as seen. */
export function useInView<T extends Element>(threshold = 0.2) {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const element = ref.current;
    if (seen || !element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { threshold },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [seen, threshold]);
  return [ref, seen] as const;
}

/** Index of the item nearest the middle of the viewport, among those observed. */
export function useActiveIndex(count: number) {
  const refs = useRef<(HTMLElement | null)[]>([]);
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.index));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.slice(0, count).forEach((element) => element && observer.observe(element));
    return () => observer.disconnect();
  }, [count]);
  const bind = (index: number) => ({
    ref: (element: HTMLElement | null) => {
      refs.current[index] = element;
    },
    "data-index": index,
  });
  return [active, bind] as const;
}
