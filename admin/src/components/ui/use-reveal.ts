import { useEffect, useRef } from "react";

/**
 * Scroll-reveal hook for the `.jn-reveal` helper (see jobnest.css). Attach the
 * returned ref to a container; every descendant with the `jn-reveal` class
 * fades/slides in as it enters the viewport, with a small stagger. Falls back
 * to immediately visible when IntersectionObserver is unavailable, and force-
 * reveals after a timeout so nothing can get stuck hidden.
 *
 * Pass `deps` when the revealed content mounts asynchronously (e.g. after a
 * data fetch) so the hook re-scans and picks up the newly rendered nodes —
 * otherwise nodes added after mount stay invisible at opacity:0.
 *
 *   const ref = useReveal([data]);   // re-scan when `data` arrives
 *   <div ref={ref}> ...<Card className="jn-reveal" />... </div>
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>(
  deps: unknown[] = [],
  stagger = 45,
) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    // Only (re)observe nodes that haven't already revealed.
    const nodes = Array.from(root.querySelectorAll<HTMLElement>(".jn-reveal:not(.in)"));
    if (!nodes.length) return;

    if (!("IntersectionObserver" in window)) {
      nodes.forEach((el) => el.classList.add("in"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) {
            en.target.classList.add("in");
            io.unobserve(en.target);
          }
        });
      },
      { threshold: 0.06 },
    );
    nodes.forEach((el, i) => {
      el.style.transitionDelay = `${Math.min(i * stagger, 400)}ms`;
      io.observe(el);
    });
    // Safety net: never leave content hidden.
    const t = window.setTimeout(() => nodes.forEach((el) => el.classList.add("in")), 2000);
    return () => {
      io.disconnect();
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}

export default useReveal;
