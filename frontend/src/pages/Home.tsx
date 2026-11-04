import { useEffect } from "react";
import { api } from "../api/client";
import type { Entry, Profile } from "../api/types";
import { Approach } from "../components/Approach";
import { Contact } from "../components/Contact";
import { Ecosystem } from "../components/Ecosystem";
import { Experience } from "../components/Experience";
import { Hero } from "../components/Hero";
import { Layout } from "../components/Layout";
import { Outside } from "../components/Outside";
import { Stack } from "../components/Stack";
import { Work, type WorkEntries } from "../components/Work";
import { useI18n } from "../i18n";
import { cvAttachment, experienceRows, learningCards, letterAttachment, stackGroups } from "../lib/derive";
import { useApi } from "../lib/useApi";

/** A failed optional request resolves to null: the section falls back to the handoff copy. */
function orNull<T>(promise: Promise<T>): Promise<T | null> {
  return promise.catch(() => null);
}

export function Home() {
  const { lang, t } = useI18n();
  const profile = useApi<Profile | null>(`profile:${lang}`, (signal) => orNull(api.profile(lang, { signal })));
  const experience = useApi<Entry[] | null>(`experience:${lang}`, (signal) => orNull(api.experience(lang, { signal })));
  const learning = useApi(`learning:${lang}`, (signal) =>
    Promise.all([
      orNull(api.education(lang, { signal })),
      orNull(api.certificates(lang, { signal })),
      orNull(api.studies(lang, { signal })),
    ]),
  );
  const skills = useApi(`skills:${lang}`, (signal) => orNull(api.skills(lang, { signal })));
  const ecosystem = useApi<Entry | null>(`ecosystem:${lang}`, (signal) => orNull(api.writing("ecosystem", lang, { signal })));
  const work = useApi<WorkEntries>(`work:${lang}`, async (signal) => {
    const slugs = ["vizzion", "vizzion-data-platform", "loopia", "rhye", "silpi", "reuni-challenge"] as const;
    const entries = await Promise.all(slugs.map((slug) => orNull(api.project(slug, lang, { signal }))));
    return Object.fromEntries(slugs.map((slug, index) => [slug, entries[index] ?? null]));
  });

  // Arriving from another page at /#section: scroll once the section exists.
  useEffect(() => {
    const target = window.location.hash.slice(1);
    if (target) document.getElementById(target)?.scrollIntoView();
  }, []);

  const cv = cvAttachment(profile.data, lang);
  const otherCv = cvAttachment(profile.data, lang === "pt" ? "en" : "pt");
  const [education, certificates, studies] = learning.data ?? [null, null, null];

  return (
    <Layout onHome cv={cv} title={t.titles.home}>
      <Hero availability={profile.data?.availability ?? null} cv={cv} />
      <Work entries={work.data ?? {}} />
      <Ecosystem entry={ecosystem.data ?? null} />
      <Approach />
      <Experience
        rows={experienceRows(experience.data, lang)}
        learning={learningCards(education, certificates, studies, undefined, lang)}
        cv={cv}
        otherCv={otherCv !== cv ? otherCv : null}
        letter={letterAttachment(profile.data, lang)}
      />
      <Stack groups={stackGroups(skills.data, lang)} />
      <Outside />
      <Contact cv={cv} />
    </Layout>
  );
}
