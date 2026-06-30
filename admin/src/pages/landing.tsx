import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { CSSProperties } from "react";
import {
  IconSpeakerphone, IconPencil, IconUsers, IconTrendingUp, IconHeart, IconShield,
  IconBriefcase, IconSchool, IconHeadset, IconClipboardCheck, IconMessage, IconLayoutDashboard,
} from "@tabler/icons-react";

import { useAuthStore } from "@/stores/auth.store";
import { STORAGE_KEYS } from "@/config/api";

/**
 * JobFlow public landing page (route "/"). A faithful 1:1 port of the
 * "JobFlow Landing" mockup — blue→violet brand, dark feature sections,
 * floating hero cards, scroll-reveal + animated stat counters + FAQ.
 * Self-contained (no admin layout); CTAs route into the app.
 */

const GRAD = "linear-gradient(90deg,#0064E5,#CE81EE)";
const gradText: CSSProperties = { background: GRAD, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" };

const CATEGORIES: { name: string; count: number; color: string; Icon: typeof IconUsers }[] = [
  { name: "Marketing & Communication", count: 66, color: "linear-gradient(135deg,#0064E5,#5a8ff0)", Icon: IconSpeakerphone },
  { name: "Design & Development", count: 98, color: "linear-gradient(135deg,#f0a24c,#e07b3a)", Icon: IconPencil },
  { name: "Human Research Development", count: 51, color: "linear-gradient(135deg,#7c5cff,#5a8ff0)", Icon: IconUsers },
  { name: "Finance Management", count: 45, color: "linear-gradient(135deg,#34c08a,#1f9e6e)", Icon: IconTrendingUp },
  { name: "Healthcare & Medical", count: 43, color: "linear-gradient(135deg,#2fc7a8,#16a085)", Icon: IconHeart },
  { name: "Aviation Guide & Security", count: 44, color: "linear-gradient(135deg,#4aa8ff,#0064E5)", Icon: IconShield },
  { name: "Business & Consulting", count: 29, color: "linear-gradient(135deg,#f5b042,#e89020)", Icon: IconBriefcase },
  { name: "Education & Training", count: 58, color: "linear-gradient(135deg,#b388f5,#8a5fe0)", Icon: IconSchool },
  { name: "Customer Support Care", count: 65, color: "linear-gradient(135deg,#6a7bf0,#4a5fd0)", Icon: IconHeadset },
  { name: "Project Management", count: 53, color: "linear-gradient(135deg,#f0935c,#e07040)", Icon: IconClipboardCheck },
  { name: "Marketing & Communication", count: 68, color: GRAD, Icon: IconMessage },
];

const JOBS = [
  { company: "TechNova", location: "San Francisco, USA", logo: "/landing/logo-technova.png", role: "Front-End Developer", tag1: "Full time", tag2: "Featured", tag2color: "#1f9e6e", tag2bg: "rgba(31,158,110,.1)", salary: "$5,500–10,000", desc: "Develop responsive user interfaces using React. Collaborate with designers and backend teams to improve UX across platforms.", posted: "5 days ago" },
  { company: "PixelCraft", location: "Remote", logo: "/landing/logo-pixelcraft.png", role: "UI/UX Designer", tag1: "Full time", tag2: "Part time", tag2color: "#0064E5", tag2bg: "rgba(0,100,229,.08)", salary: "$2,500–7,000", desc: "Work closely with product teams to design intuitive, user-friendly interfaces. Portfolio required. Remote work available.", posted: "1 day ago" },
  { company: "SecureMind", location: "Singapore", logo: "/landing/logo-securemind.png", role: "Cybersecurity Analyst", tag1: "Full time", tag2: "Urgent", tag2color: "#e0533a", tag2bg: "rgba(224,83,58,.1)", salary: "$5,500–9,000", desc: "Monitor network activity, detect threats, and respond to incidents in real time. Experience with firewalls and SIEM tools required.", posted: "2 days ago" },
];

const FAQS = [
  { q: "How do I apply for a job on JobFlow?", a: "To apply for a job on JobFlow, simply sign up for a free account and complete your profile. Then, browse through curated job listings based on your skills and interests. When you find a job you like, click “Apply Now” to send your CV instantly. You’ll also get personalized job alerts sent directly to your dashboard." },
  { q: "What is JobFlow?", a: "JobFlow is a modern job platform that connects talented job seekers with trusted employers worldwide. We focus on matching people to roles that fit their real skills and ambitions, not just their resume." },
  { q: "How can I get better job matches?", a: "Complete your profile fully, highlight your real skills and projects, and keep your preferences up to date. Our matching engine uses this to surface roles that genuinely fit your potential." },
  { q: "How often are new jobs posted on JobFlow?", a: "New roles are posted every day across every industry. Turn on job alerts to be notified the moment a matching opportunity goes live." },
  { q: "Can I save job listings for later?", a: "Yes. Bookmark any job to your dashboard and revisit it whenever you're ready to apply. Saved jobs sync across all your devices." },
];

function MsSquares({ s = 13, g = 3 }: { s?: number; g?: number }) {
  return (
    <span style={{ display: "grid", gridTemplateColumns: `${s}px ${s}px`, gridTemplateRows: `${s}px ${s}px`, gap: g }}>
      <i style={{ background: "#F25022", borderRadius: 1 }} />
      <i style={{ background: "#7FBA00", borderRadius: 1 }} />
      <i style={{ background: "#00A4EF", borderRadius: 1 }} />
      <i style={{ background: "#FFB900", borderRadius: 1 }} />
    </span>
  );
}

const gradBtn: CSSProperties = { border: "none", cursor: "pointer", color: "#fff", fontFamily: "inherit", background: GRAD };

export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  // Public page: show a logged-in nav when a session exists. Resolve the user
  // from the token on mount so the avatar/name can render.
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const checkAuth = useAuthStore((s) => s.checkAuth);
  const logout = useAuthStore((s) => s.logout);
  const loggedIn = isAuthenticated || !!localStorage.getItem(STORAGE_KEYS.accessToken);
  useEffect(() => {
    if (!isAuthenticated && localStorage.getItem(STORAGE_KEYS.accessToken)) void checkAuth();
  }, [isAuthenticated, checkAuth]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reveals = Array.from(root.querySelectorAll<HTMLElement>(".lp-reveal"));
    const counters = () => {
      const block = root.querySelector("#lp-stats");
      if (!block) return null;
      return new IntersectionObserver((entries, obs) => {
        entries.forEach((en) => {
          if (!en.isIntersecting) return;
          obs.disconnect();
          ([[0, 10], [1, 3], [2, 95]] as const).forEach(([i, target]) => {
            const el = root.querySelector<HTMLElement>(`#lp-stat-${i}`);
            if (!el) return;
            const start = performance.now();
            const step = (now: number) => {
              const p = Math.min((now - start) / 1500, 1);
              el.textContent = String(Math.round((1 - Math.pow(1 - p, 3)) * target));
              if (p < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
          });
        });
      }, { threshold: 0.4 });
    };

    if (!("IntersectionObserver" in window)) {
      reveals.forEach((el) => el.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    reveals.forEach((el) => io.observe(el));
    const fallback = window.setTimeout(() => reveals.forEach((el) => el.classList.add("in")), 3500);
    const co = counters();
    const block = root.querySelector("#lp-stats");
    if (co && block) co.observe(block);
    return () => { io.disconnect(); co?.disconnect(); window.clearTimeout(fallback); };
  }, []);

  return (
    <div ref={rootRef} style={{ position: "relative", overflow: "hidden", background: "#fff", color: "#202020", fontFamily: "Inter, sans-serif" }}>
      <style>{`
        .lp-reveal{opacity:0;transform:translateY(36px);transition:opacity .8s cubic-bezier(.2,.7,.2,1),transform .8s cubic-bezier(.2,.7,.2,1)}
        .lp-reveal.in{opacity:1;transform:none}
        @keyframes lpFloatA{0%,100%{transform:translateY(0)}50%{transform:translateY(-16px)}}
        @keyframes lpFloatB{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-22px) rotate(-4deg)}}
        @keyframes lpFloatC{0%,100%{transform:translateY(0) rotate(3deg)}50%{transform:translateY(-12px) rotate(3deg)}}
        @keyframes lpDrift{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(50px,-40px) scale(1.15)}}
        @keyframes lpDrift2{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-44px,36px) scale(1.1)}}
        .lp-link{transition:color .2s}.lp-link:hover{color:#0064E5}
        .lp-lift{transition:transform .25s,box-shadow .25s}.lp-lift:hover{transform:translateY(-2px)}
        .lp-lift3{transition:transform .25s,box-shadow .25s}.lp-lift3:hover{transform:translateY(-3px)}
        .lp-cat{transition:transform .3s,box-shadow .3s,border-color .3s}.lp-cat:hover{transform:translateY(-6px);box-shadow:0 18px 40px rgba(20,20,40,.10);border-color:#E0D4F5}
        .lp-job{transition:transform .35s,box-shadow .35s}.lp-job:hover{transform:translateY(-8px);box-shadow:0 26px 56px rgba(20,20,40,.12)}
        .lp-faq-ans{max-height:0;overflow:hidden;opacity:0;transition:max-height .5s ease,opacity .4s ease,margin .5s ease}
        .lp-faq.open .lp-faq-ans{max-height:360px;opacity:1;margin-top:14px}
        .lp-faq-icon{transition:transform .4s cubic-bezier(.2,.7,.2,1)}
        .lp-faq.open .lp-faq-icon{transform:rotate(45deg)}
        .lp-faq.open{border-color:#CE81EE !important;box-shadow:0 14px 40px rgba(99,76,210,.12)}
        .lp-social{transition:background .25s,color .25s}.lp-social:hover{background:linear-gradient(135deg,#0064E5,#CE81EE);color:#fff}
      `}</style>

      {/* NAV */}
      <nav style={{ position: "sticky", top: 0, zIndex: 60, backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)", background: "rgba(255,255,255,.78)", borderBottom: "1px solid #EAEAEA" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", padding: "16px 40px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontWeight: 700, fontSize: 22, letterSpacing: "-.02em" }}>.JobFlow</span>
          <div style={{ display: "flex", gap: 38, alignItems: "center" }}>
            {["Jobs", "Companies", "Career Resources", "For Employers"].map((l) => (
              <a key={l} href="#" className="lp-link" style={{ textDecoration: "none", color: "#3a3a3a", fontSize: 15, fontWeight: 500 }}>{l}</a>
            ))}
          </div>
          {loggedIn ? (
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <button type="button" onClick={logout} className="lp-link" style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: "inherit", color: "#202020", fontSize: 15, fontWeight: 600 }}>Log Out</button>
              <Link to="/admin" className="lp-lift" style={{ ...gradBtn, textDecoration: "none", fontSize: 15, fontWeight: 600, padding: "10px 22px 10px 12px", borderRadius: 30, boxShadow: "0 8px 22px rgba(99,76,210,.28)", display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ width: 30, height: 30, borderRadius: "50%", background: "rgba(255,255,255,.22)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 14 }}>
                  {(user?.username || user?.email || "A").charAt(0).toUpperCase()}
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <IconLayoutDashboard size={16} />
                  Dashboard
                </span>
              </Link>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
              <Link to="/login" style={{ textDecoration: "none", color: "#202020", fontSize: 15, fontWeight: 600 }}>Log In</Link>
              <Link to="/login" className="lp-lift" style={{ ...gradBtn, textDecoration: "none", fontSize: 15, fontWeight: 600, padding: "11px 26px", borderRadius: 30, boxShadow: "0 8px 22px rgba(99,76,210,.28)" }}>Sign Up</Link>
            </div>
          )}
        </div>
      </nav>

      {/* HERO */}
      <header style={{ position: "relative", overflow: "hidden", padding: "70px 40px 90px" }}>
        <div style={{ position: "absolute", top: -120, left: -100, width: 480, height: 480, borderRadius: "50%", background: "radial-gradient(circle,rgba(0,100,229,.16),transparent 65%)", animation: "lpDrift 16s ease-in-out infinite", pointerEvents: "none" }} />
        <div style={{ position: "absolute", bottom: -160, right: -80, width: 520, height: 520, borderRadius: "50%", background: "radial-gradient(circle,rgba(206,129,238,.18),transparent 65%)", animation: "lpDrift2 18s ease-in-out infinite", pointerEvents: "none" }} />
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "grid", gridTemplateColumns: "1.05fr .95fr", gap: 40, alignItems: "center", position: "relative" }}>
          <div className="lp-reveal">
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "7px 16px", borderRadius: 30, background: "rgba(0,100,229,.07)", border: "1px solid rgba(0,100,229,.14)", fontSize: 13, fontWeight: 600, color: "#0064E5", marginBottom: 24 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: GRAD }} />
              Over 12,000 fresh roles this month
            </div>
            <h1 style={{ fontSize: 58, lineHeight: 1.04, fontWeight: 800, letterSpacing: "-.03em", margin: "0 0 22px" }}>Your Next Job Is<br />Just One <span style={gradText}>Click Away</span></h1>
            <p style={{ fontSize: 18, lineHeight: 1.6, color: "#5f5f5f", maxWidth: 480, margin: "0 0 34px" }}>Find opportunities that match your passion, not just your resume. Let's build the career you deserve — starting today.</p>

            <div style={{ display: "flex", alignItems: "center", background: "#fff", border: "1px solid #EAEAEA", borderRadius: 40, padding: "8px 8px 8px 22px", boxShadow: "0 18px 50px rgba(20,20,40,.10)", maxWidth: 520, gap: 10 }}>
              <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#9a9a9a", letterSpacing: ".04em", textTransform: "uppercase" }}>Job title or keyword</span>
                <input placeholder="e.g. Product Designer" style={{ border: "none", outline: "none", fontFamily: "inherit", fontSize: 15, color: "#202020", padding: "2px 0", background: "transparent", width: "100%" }} />
              </div>
              <div style={{ width: 1, height: 34, background: "#EAEAEA" }} />
              <div style={{ display: "flex", flexDirection: "column", width: 120 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#9a9a9a", letterSpacing: ".04em", textTransform: "uppercase" }}>Location</span>
                <input placeholder="Remote" style={{ border: "none", outline: "none", fontFamily: "inherit", fontSize: 15, color: "#202020", padding: "2px 0", background: "transparent", width: "100%" }} />
              </div>
              <Link to="/login" className="lp-lift" style={{ ...gradBtn, fontWeight: 600, fontSize: 15, padding: "14px 30px", borderRadius: 30, boxShadow: "0 8px 20px rgba(99,76,210,.3)", textDecoration: "none" }}>Search</Link>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 34 }}>
              <div style={{ display: "flex" }}>
                {["face-1", "face-3", "face-6", "face-5"].map((f, i) => (
                  <img key={f} src={`/landing/${f}.png`} alt="" style={{ width: 40, height: 40, borderRadius: "50%", border: "2.5px solid #fff", objectFit: "cover", marginLeft: i ? -12 : 0, boxShadow: "0 2px 8px rgba(0,0,0,.12)" }} />
                ))}
              </div>
              <span style={{ fontSize: 15, color: "#5f5f5f" }}><strong style={{ color: "#202020" }}>Trusted by 100,000+</strong> people</span>
            </div>
          </div>

          {/* floating cards */}
          <div className="lp-reveal" style={{ position: "relative", height: 520 }}>
            <div style={{ position: "absolute", top: 40, left: 30, right: 10, background: "#fff", border: "1px solid #EFEFEF", borderRadius: 22, padding: 24, boxShadow: "0 30px 70px rgba(20,20,40,.14)", animation: "lpFloatA 7s ease-in-out infinite", zIndex: 2 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18 }}>
                <span style={{ width: 50, height: 50, borderRadius: 13, background: "#fff", border: "1px solid #ECECEC", boxShadow: "0 2px 8px rgba(0,0,0,.06)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><MsSquares /></span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 18 }}>Microsoft</div>
                  <div style={{ fontSize: 13, color: "#9a9a9a" }}>WA, USA</div>
                </div>
                <span style={{ marginLeft: "auto", width: 34, height: 34, borderRadius: 10, background: "#F5F5F7", display: "flex", alignItems: "center", justifyContent: "center", color: "#9a9a9a", fontSize: 18 }}>♡</span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 20, marginBottom: 12 }}>Product Manager</div>
              <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#0064E5", background: "rgba(0,100,229,.08)", padding: "6px 12px", borderRadius: 20 }}>Full time</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#7a7a7a", background: "#F5F5F7", padding: "6px 12px", borderRadius: 20 }}>Permanent</span>
              </div>
              <p style={{ fontSize: 13.5, lineHeight: 1.55, color: "#6b6b6b", margin: "0 0 18px" }}>Work with teams to build and launch Microsoft 365 features. Hybrid work available.</p>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 700, fontSize: 16 }}>$5,500–10,000<span style={{ fontSize: 12, color: "#9a9a9a", fontWeight: 500 }}>/Month</span></span>
                <button style={{ ...gradBtn, fontWeight: 600, fontSize: 13, padding: "10px 22px", borderRadius: 24 }}>Apply Now</button>
              </div>
            </div>

            <div style={{ position: "absolute", top: -14, right: -18, background: "#fff", border: "1px solid #EFEFEF", borderRadius: 18, padding: "16px 18px", boxShadow: "0 22px 50px rgba(20,20,40,.12)", animation: "lpFloatB 8s ease-in-out infinite", zIndex: 3, width: 210 }}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>Top Companies Hiring Now</div>
              <div style={{ display: "flex", alignItems: "center", marginBottom: 13 }}>
                <span style={{ width: 32, height: 32, borderRadius: 9, background: "#fff", border: "1px solid #ECECEC", boxShadow: "0 2px 6px rgba(0,0,0,.08)", display: "flex", alignItems: "center", justifyContent: "center" }}><MsSquares s={9} g={2} /></span>
                {[
                  { c: "#4285F4", t: "G" }, { c: "#232F3E", t: "a" }, { c: "#0668E1", t: "∞" }, { c: "#E50914", t: "N" },
                ].map((b, i) => (
                  <span key={i} style={{ width: 32, height: 32, borderRadius: 9, background: "#fff", border: "1px solid #ECECEC", boxShadow: "0 2px 6px rgba(0,0,0,.08)", display: "flex", alignItems: "center", justifyContent: "center", marginLeft: -6, fontWeight: 800, fontSize: 17, color: b.c }}>{b.t}</span>
                ))}
                <span style={{ width: 32, height: 32, borderRadius: 9, background: "#F5F5F7", color: "#8a8a8a", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, marginLeft: -6, border: "1px solid #ECECEC" }}>+9</span>
              </div>
              <a href="#" style={{ textDecoration: "none", fontSize: 12, fontWeight: 600, color: "#0064E5" }}>View Jobs →</a>
            </div>

            <div style={{ position: "absolute", bottom: 6, left: -22, background: "#fff", border: "1px solid #EFEFEF", borderRadius: 18, padding: "16px 18px", boxShadow: "0 22px 50px rgba(20,20,40,.12)", animation: "lpFloatC 9s ease-in-out infinite", zIndex: 3, width: 208 }}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>Highest-Paying Sectors</div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
                <span style={{ fontSize: 13, color: "#3a3a3a" }}>UI/UX Designer</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#1f9e6e" }}>+18%</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, color: "#3a3a3a" }}>Data Scientist</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#1f9e6e" }}>+24%</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* CATEGORIES */}
      <section style={{ padding: "90px 40px", maxWidth: 1240, margin: "0 auto" }}>
        <div className="lp-reveal" style={{ textAlign: "center", marginBottom: 54 }}>
          <h2 style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-.025em", margin: "0 0 16px" }}>Explore <span style={gradText}>Careers</span> Across Every Field</h2>
          <p style={{ fontSize: 17, lineHeight: 1.6, color: "#5f5f5f", maxWidth: 680, margin: "0 auto" }}>Discover a wide range of careers across every industry — from design and tech to healthcare and finance. Find roles that match your skills and passion, and take the next step toward your dream job.</p>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 18, justifyContent: "center" }}>
          {CATEGORIES.map((cat, i) => (
            <div key={i} className="lp-reveal lp-cat" style={{ display: "flex", alignItems: "center", gap: 14, background: "#fff", border: "1px solid #EFEFEF", borderRadius: 18, padding: "18px 24px", width: 316, cursor: "pointer" }}>
              <span style={{ width: 46, height: 46, borderRadius: 14, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: cat.color }}>
                <cat.Icon size={24} color="#fff" stroke={2} />
              </span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{cat.name}</div>
                <div style={{ fontSize: 13, color: "#9a9a9a" }}>{cat.count} Jobs Available</div>
              </div>
            </div>
          ))}
        </div>
        <div className="lp-reveal" style={{ textAlign: "center", marginTop: 46 }}>
          <button className="lp-lift3" style={{ ...gradBtn, fontWeight: 600, fontSize: 16, padding: "14px 38px", borderRadius: 30, boxShadow: "0 10px 26px rgba(99,76,210,.3)" }}>Explore All</button>
        </div>
      </section>

      {/* STATS (dark) */}
      <section style={{ padding: "30px 40px 90px", maxWidth: 1240, margin: "0 auto" }}>
        <div className="lp-reveal" id="lp-stats" style={{ position: "relative", overflow: "hidden", background: "#202020", borderRadius: 36, padding: "84px 64px", color: "#fff", textAlign: "center" }}>
          <div style={{ position: "absolute", top: -80, right: -40, width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle,rgba(99,76,210,.55),transparent 65%)", animation: "lpDrift 14s ease-in-out infinite" }} />
          <div style={{ position: "absolute", bottom: -120, left: -60, width: 320, height: 320, borderRadius: "50%", background: "radial-gradient(circle,rgba(206,129,238,.35),transparent 65%)", animation: "lpDrift2 17s ease-in-out infinite" }} />
          <h2 style={{ position: "relative", fontSize: 38, lineHeight: 1.25, fontWeight: 800, letterSpacing: "-.02em", maxWidth: 880, margin: "0 auto 56px" }}>We've built a trusted ecosystem that supports thousands of job seekers and recruiters around the globe — <span style={{ background: "linear-gradient(90deg,#6ea8ff,#CE81EE)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>fast, reliable, and results-driven.</span></h2>
          <div style={{ position: "relative", display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 30, marginBottom: 52 }}>
            {[
              { id: "lp-stat-0", suffix: "K", label: "Job matches made through JobFlow" },
              { id: "lp-stat-1", suffix: "K", label: "Verified employers onboard" },
              { id: "lp-stat-2", suffix: "%", label: "Satisfaction rate from both talents and companies" },
              { fixed: "24/7", label: "Dedicated support to guide your hiring or job search journey" },
            ].map((s, i) => (
              <div key={i}>
                <div style={{ fontSize: 52, fontWeight: 800, letterSpacing: "-.03em" }}>
                  {s.fixed ?? <><span id={s.id}>0</span>{s.suffix}</>}
                </div>
                <div style={{ fontSize: 14, color: "#b1b1b1", marginTop: 8, lineHeight: 1.5 }}>{s.label}</div>
              </div>
            ))}
          </div>
          <button className="lp-lift3" style={{ position: "relative", ...gradBtn, fontWeight: 600, fontSize: 16, padding: "14px 38px", borderRadius: 30, boxShadow: "0 10px 26px rgba(99,76,210,.4)" }}>Join Us Today</button>
        </div>
      </section>

      {/* POPULAR JOBS */}
      <section style={{ padding: "60px 40px 90px", maxWidth: 1240, margin: "0 auto" }}>
        <div className="lp-reveal" style={{ textAlign: "center", marginBottom: 54 }}>
          <h2 style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-.025em", margin: "0 0 14px" }}>Popular Jobs</h2>
          <p style={{ fontSize: 17, color: "#5f5f5f", margin: 0 }}>See companies are hiring now — and you could be their next great hire.</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 26 }}>
          {JOBS.map((job, i) => (
            <div key={i} className="lp-reveal lp-job" style={{ background: "#fff", border: "1px solid #EFEFEF", borderRadius: 22, padding: 28 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 20 }}>
                <div role="img" aria-label={job.company} style={{ width: 52, height: 52, borderRadius: 14, flexShrink: 0, border: "1px solid #EFEFEF", background: `#f2f2f2 url('${job.logo}') center/cover no-repeat` }} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: 17 }}>{job.company}</div>
                  <div style={{ fontSize: 13, color: "#9a9a9a" }}>{job.location}</div>
                </div>
              </div>
              <div style={{ fontWeight: 700, fontSize: 20, marginBottom: 14 }}>{job.role}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#0064E5", background: "rgba(0,100,229,.08)", padding: "6px 12px", borderRadius: 20 }}>{job.tag1}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: job.tag2color, background: job.tag2bg, padding: "6px 12px", borderRadius: 20 }}>{job.tag2}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#7a7a7a", background: "#F5F5F7", padding: "6px 12px", borderRadius: 20 }}>Permanent</span>
              </div>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: "#6b6b6b", margin: "0 0 22px", minHeight: 66 }}>{job.desc}</p>
              <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 18 }}>{job.salary}<span style={{ fontSize: 12, color: "#9a9a9a", fontWeight: 500 }}>/Month</span></div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <button className="lp-lift" style={{ ...gradBtn, fontWeight: 600, fontSize: 14, padding: "11px 26px", borderRadius: 24 }}>Apply Now</button>
                <span style={{ fontSize: 13, color: "#9a9a9a" }}>{job.posted}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="lp-reveal" style={{ textAlign: "center", marginTop: 46 }}>
          <a href="#" style={{ textDecoration: "none", fontSize: 16, fontWeight: 600, color: "#0064E5" }}>Explore All →</a>
        </div>
      </section>

      {/* TESTIMONIAL */}
      <section style={{ padding: "70px 40px", maxWidth: 760, margin: "0 auto", textAlign: "center" }}>
        <div className="lp-reveal">
          <h2 style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-.025em", margin: "0 0 40px" }}>What Our Users Say</h2>
          <div style={{ fontSize: 60, lineHeight: 1, ...gradText, fontWeight: 800, marginBottom: 6 }}>"</div>
          <p style={{ fontSize: 24, lineHeight: 1.55, fontWeight: 500, color: "#202020", margin: "0 0 28px" }}>I used to struggle with job platforms, but JobFlow makes it feel easy and personal. It actually understands what I'm looking for.</p>
          <div style={{ fontWeight: 700, fontSize: 17 }}>Esther Howard</div>
          <div style={{ fontSize: 14, color: "#9a9a9a", marginBottom: 26 }}>Marketing Coordinator</div>
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
            <img src="/landing/face-7.png" alt="" style={{ width: 44, height: 44, borderRadius: "50%", border: "2.5px solid #fff", objectFit: "cover", boxShadow: "0 2px 10px rgba(0,0,0,.12)" }} />
            <img src="/landing/face-6.png" alt="Esther Howard" style={{ width: 60, height: 60, borderRadius: "50%", border: "3px solid #fff", objectFit: "cover", margin: "0 -10px", position: "relative", zIndex: 2, boxShadow: "0 6px 18px rgba(0,0,0,.18)" }} />
            <img src="/landing/face-8.png" alt="" style={{ width: 44, height: 44, borderRadius: "50%", border: "2.5px solid #fff", objectFit: "cover", boxShadow: "0 2px 10px rgba(0,0,0,.12)" }} />
          </div>
        </div>
      </section>

      {/* STATEMENT */}
      <section style={{ padding: "80px 40px", maxWidth: 1000, margin: "0 auto", textAlign: "center" }}>
        <h2 className="lp-reveal" style={{ fontSize: 40, lineHeight: 1.4, fontWeight: 700, letterSpacing: "-.02em", margin: 0, color: "#202020" }}>Creating a clearer path for job seekers and connecting employers with the right talent is essential for building a <span style={gradText}>more intelligent workforce</span> in the future.</h2>
      </section>

      {/* NEXT-LEVEL (dark) */}
      <section style={{ padding: "40px 40px 90px", maxWidth: 1240, margin: "0 auto" }}>
        <div className="lp-reveal" style={{ position: "relative", overflow: "hidden", background: "#202020", borderRadius: 36, padding: "70px 64px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 50, alignItems: "center" }}>
          <div style={{ position: "absolute", top: -100, left: "30%", width: 340, height: 340, borderRadius: "50%", background: "radial-gradient(circle,rgba(99,76,210,.4),transparent 65%)", animation: "lpDrift 15s ease-in-out infinite" }} />
          <div style={{ position: "relative", height: 380 }}>
            <div style={{ position: "absolute", top: 0, left: 10, width: 300, background: "#fff", borderRadius: 20, padding: 22, boxShadow: "0 30px 60px rgba(0,0,0,.4)", animation: "lpFloatA 7s ease-in-out infinite" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <img src="/landing/logo-securemind.png" alt="SecureMind" style={{ width: 46, height: 46, borderRadius: 13, objectFit: "cover" }} />
                <div><div style={{ fontWeight: 700, fontSize: 16 }}>SecureMind</div><div style={{ fontSize: 12, color: "#9a9a9a" }}>Singapore</div></div>
              </div>
              <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 10 }}>Cybersecurity Analyst</div>
              <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#0064E5", background: "rgba(0,100,229,.08)", padding: "5px 11px", borderRadius: 18 }}>Full time</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#e0533a", background: "rgba(224,83,58,.1)", padding: "5px 11px", borderRadius: 18 }}>Urgent</span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>$5,500–9,000<span style={{ fontSize: 11, color: "#9a9a9a", fontWeight: 500 }}>/Month</span></div>
            </div>
            <div style={{ position: "absolute", bottom: 10, right: 0, width: 250, background: "#fff", borderRadius: 20, padding: 18, boxShadow: "0 24px 50px rgba(0,0,0,.35)", animation: "lpFloatC 9s ease-in-out infinite" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>Video stream Project</span>
                <span style={{ fontSize: 10, fontWeight: 600, color: "#1f9e6e", background: "rgba(31,158,110,.12)", padding: "4px 9px", borderRadius: 14 }}>In Progress</span>
              </div>
              <div style={{ position: "relative", borderRadius: 12, overflow: "hidden", marginBottom: 12 }}>
                <img src="/landing/video-thumb.png" alt="" style={{ width: "100%", height: 96, objectFit: "cover", display: "block" }} />
                <span style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 34, height: 34, borderRadius: "50%", background: "rgba(255,255,255,.92)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 12px rgba(0,0,0,.25)" }}>
                  <span style={{ borderLeft: "11px solid #202020", borderTop: "7px solid transparent", borderBottom: "7px solid transparent", marginLeft: 3 }} />
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <img src="/landing/face-esther.png" alt="" style={{ width: 32, height: 32, borderRadius: 9, objectFit: "cover" }} />
                <div><div style={{ fontSize: 13, fontWeight: 600 }}>Client</div><div style={{ fontSize: 11, color: "#9a9a9a" }}>Independent</div></div>
              </div>
            </div>
          </div>
          <div style={{ position: "relative", color: "#fff" }}>
            <h2 style={{ fontSize: 36, lineHeight: 1.2, fontWeight: 800, letterSpacing: "-.02em", margin: "0 0 26px", background: "linear-gradient(90deg,#6ea8ff,#CE81EE)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>Next-Level Opportunities, All in One Place</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 18, marginBottom: 34 }}>
              {[
                "Build your profile to showcase real skills, not just job titles",
                "Discover high-quality opportunities that match your potential",
                "Connect with trusted employers who are hiring globally",
              ].map((line, i) => (
                <div key={i} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  <span style={{ width: 26, height: 26, borderRadius: "50%", flexShrink: 0, background: "linear-gradient(135deg,#0064E5,#CE81EE)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 14, fontWeight: 700 }}>✓</span>
                  <span style={{ fontSize: 16, color: "#d8d8d8", lineHeight: 1.5 }}>{line}</span>
                </div>
              ))}
            </div>
            <button className="lp-lift3" style={{ ...gradBtn, fontWeight: 600, fontSize: 16, padding: "14px 34px", borderRadius: 30, boxShadow: "0 10px 26px rgba(99,76,210,.45)" }}>Start Exploring Now</button>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section style={{ padding: "60px 40px 90px", maxWidth: 880, margin: "0 auto" }}>
        <h2 className="lp-reveal" style={{ textAlign: "center", fontSize: 42, fontWeight: 800, letterSpacing: "-.025em", margin: "0 0 48px" }}>Frequently Asked Questions</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {FAQS.map((f, i) => (
            <div key={i} className={`lp-faq${openFaq === i ? " open" : ""}`} onClick={() => setOpenFaq(openFaq === i ? null : i)}
              style={{ background: "#fff", border: "1px solid #EAEAEA", borderRadius: 16, padding: "26px 28px", cursor: "pointer", transition: "border-color .3s,box-shadow .3s" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                <span style={{ fontWeight: 600, fontSize: 19 }}>{f.q}</span>
                <span className="lp-faq-icon" style={{ fontSize: 26, color: "#0064E5", flexShrink: 0, lineHeight: 1 }}>+</span>
              </div>
              <div className="lp-faq-ans" style={{ fontSize: 15, lineHeight: 1.65, color: "#5f5f5f" }}>{f.a}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA (dark) */}
      <section style={{ padding: "40px 40px 90px", maxWidth: 1240, margin: "0 auto" }}>
        <div className="lp-reveal" style={{ position: "relative", overflow: "hidden", background: "#202020", borderRadius: 36, padding: "80px 64px", textAlign: "center", color: "#fff" }}>
          <div style={{ position: "absolute", top: -90, right: "10%", width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle,rgba(206,129,238,.4),transparent 65%)", animation: "lpDrift2 16s ease-in-out infinite" }} />
          <h2 style={{ position: "relative", fontSize: 42, fontWeight: 800, letterSpacing: "-.025em", margin: "0 0 18px" }}>Let's Talk! <span style={{ background: "linear-gradient(90deg,#6ea8ff,#CE81EE)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>We're Here to Help</span></h2>
          <p style={{ position: "relative", fontSize: 17, lineHeight: 1.6, color: "#b1b1b1", maxWidth: 640, margin: "0 auto 32px" }}>Have a question, feedback, or just want to say hi? Our team is ready to support you — whether you're a job seeker, recruiter, or just curious about what we do.</p>
          <button className="lp-lift3" style={{ position: "relative", ...gradBtn, fontWeight: 600, fontSize: 16, padding: "14px 38px", borderRadius: 30, boxShadow: "0 10px 26px rgba(99,76,210,.5)" }}>Contact Us</button>
        </div>
      </section>

      {/* FOOTER */}
      <footer style={{ borderTop: "1px solid #EAEAEA", padding: "64px 40px 0" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr", gap: 50, paddingBottom: 48 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 22, marginBottom: 18 }}>.JobFlow</div>
            <div style={{ fontWeight: 700, fontSize: 20, marginBottom: 12 }}>Stay Connected With JobFlow</div>
            <p style={{ fontSize: 14, lineHeight: 1.6, color: "#7a7a7a", maxWidth: 340, margin: "0 0 22px" }}>Follow us on social media to never miss a job opportunity, career insights, and expert hiring tips.</p>
            <div style={{ display: "flex", gap: 12 }}>
              {["in", "X", "f"].map((s) => (
                <span key={s} className="lp-social" style={{ width: 40, height: 40, borderRadius: "50%", background: "#F5F5F7", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 14, color: "#3a3a3a", cursor: "pointer" }}>{s}</span>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 15, color: "#b1b1b1", fontWeight: 500, marginBottom: 18 }}>Navigation</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
              {["Job", "Companies", "Career Resources", "For Employers"].map((l) => (
                <a key={l} href="#" className="lp-link" style={{ textDecoration: "none", color: "#3a3a3a", fontSize: 15 }}>{l}</a>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 15, color: "#b1b1b1", fontWeight: 500, marginBottom: 18 }}>Our address</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 13, fontSize: 15, color: "#3a3a3a" }}>
              <span>+44 865 077 802</span>
              <span>contact@JobFlow.com</span>
              <span style={{ lineHeight: 1.5 }}>35 To Vinh Dien str, Thanh<br />Yuan, Hanoi, Vietnam</span>
            </div>
          </div>
        </div>
        <div style={{ borderTop: "1px solid #EAEAEA", padding: "26px 0", textAlign: "center" }}>
          <span style={{ fontSize: 13, color: "#9a9a9a" }}>Copyrights 2025 JobFlow. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
}
