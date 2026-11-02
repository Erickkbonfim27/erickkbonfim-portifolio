const WAVE =
  "M0 40 Q25 {a} 50 40 T100 40 T150 40 T200 40 T250 40 T300 40 T350 40 T400 40 T450 40 T500 40 T550 40 T600 40 T650 40 T700 40 T750 40 T800 40 T850 40 T900 40 T950 40 T1000 40 T1050 40 T1100 40 T1150 40 T1200 40 T1250 40 T1300 40 T1350 40 T1400 40 T1450 40 T1500 40 T1550 40 T1600 40";

const TECH = ["CS50 · HarvardX", "Spring Boot 3", "Hugging Face & Optimum", "GeoPandas", "OpenCV", "Go & Gin", "C++ & STL", "Clustering", "AWS Data Lake", "Django REST Framework"];
const OTHER = ["Tax Law", "LGPD", "Contract Theory", "Criminal Law · OAB review", "Executive Coaching", "Neuroscience Applied to Sales", "Capital Markets", "Quantum Mechanics", "Public Speaking", "Mindfulness"];

function Marquee({ tags, reverse }: { tags: string[]; reverse?: boolean }) {
  // The list is rendered twice so the -50% translate loops seamlessly.
  return (
    <div className="mq" aria-hidden="true">
      <div className={reverse ? "mq-track rev" : "mq-track"}>
        {[...tags, ...tags].map((tag, index) => (
          <span key={index} className="tag">
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

export function Outside() {
  return (
    <section id="outside" className="sec" aria-labelledby="out-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">05</span>Outside work
            </p>
            <h2 id="out-title" className="h2">
              Off the clock
            </h2>
          </div>
          <p className="r">Things that don't fit on a CV but probably explain a few things on it.</p>
        </div>
        <div className="bento">
          <article className="card dark pcard s5 reveal" style={{ overflow: "hidden" }}>
            <span className="label mono">Curious about</span>
            <h3 className="ptitle" style={{ fontSize: 26, lineHeight: 1.2 }}>
              Quantum mechanics and complex systems
            </h3>
            <p className="ptext">
              They're good teachers on thinking about uncertainty, which is most of the job when you work with LLMs.
            </p>
            <div className="wave" aria-hidden="true">
              <svg className="w1" width="1600" height="80" viewBox="0 0 1600 80" fill="none">
                <path d={WAVE.replace("{a}", "6")} stroke="currentColor" strokeWidth="2" />
              </svg>
              <svg className="w2" width="1600" height="80" viewBox="0 0 1600 80" fill="none">
                <path d={WAVE.replace("{a}", "22")} stroke="currentColor" strokeWidth="1.5" />
              </svg>
            </div>
            <p className="pfoot mono">STANFORD ONLINE HIGH SCHOOL · QUANTUM MECHANICS</p>
          </article>
          <article className="card pcard s7 reveal" style={{ overflow: "hidden" }}>
            <div className="card-top">
              <span className="label mono">Course collector</span>
              <span className="mono" style={{ fontSize: 12, color: "#5F6670" }}>
                all on my CV
              </span>
            </div>
            <p style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "8px 16px" }}>
              <span style={{ fontSize: "clamp(56px, 6cqi, 88px)", fontWeight: 600, letterSpacing: "-0.06em", lineHeight: 0.9 }}>
                70+
              </span>
              <span style={{ fontSize: 16, lineHeight: 1.55, color: "#4A505A", maxWidth: 360 }}>
                courses, from CS50 and Spring Boot to Brazilian tax law and executive coaching. I can't stop.
              </span>
            </p>
            <Marquee tags={TECH} />
            <Marquee tags={OTHER} reverse />
            <p className="sr">
              Examples: CS50, Spring Boot 3, Hugging Face, GeoPandas, OpenCV, Go and Gin, C++, tax law, LGPD, contract
              theory, executive coaching, neuroscience applied to sales, capital markets and quantum mechanics.
            </p>
          </article>
        </div>
      </div>
    </section>
  );
}
