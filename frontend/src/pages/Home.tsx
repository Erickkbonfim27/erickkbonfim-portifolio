import { useEffect } from "react";
import { api } from "../api/client";
import type { Entry, Profile } from "../api/types";
import { Approach } from "../components/Approach";
import { Contact } from "../components/Contact";
import { Experience } from "../components/Experience";
import { Hero } from "../components/Hero";
import { Layout } from "../components/Layout";
import { Outside } from "../components/Outside";
import { Stack } from "../components/Stack";
import { Work, type WorkEntries } from "../components/Work";
import { cvAttachment, experienceRows, learningCards, stackGroups } from "../lib/derive";
import { useApi } from "../lib/useApi";

/** A failed optional request resolves to null: the section falls back to the handoff copy. */
function orNull<T>(promise: Promise<T>): Promise<T | null> {
  return promise.catch(() => null);
}

export function Home() {
  const profile = useApi<Profile | null>("profile", (signal) => orNull(api.profile({ signal })));
  const experience = useApi<Entry[] | null>("experience", (signal) => orNull(api.experience({ signal })));
  const learning = useApi("learning", (signal) =>
    Promise.all([
      orNull(api.education({ signal })),
      orNull(api.certificates({ signal })),
      orNull(api.studies({ signal })),
    ]),
  );
  const skills = useApi("skills", (signal) => orNull(api.skills({ signal })));
  const work = useApi<WorkEntries>("work", async (signal) => {
    const slugs = ["vizzion", "vizzion-data-platform", "loopia", "rhye"] as const;
    const entries = await Promise.all(slugs.map((slug) => orNull(api.project(slug, { signal }))));
    return Object.fromEntries(slugs.map((slug, index) => [slug, entries[index] ?? null]));
  });

  // Arriving from another page at /#section: scroll once the section exists.
  useEffect(() => {
    const target = window.location.hash.slice(1);
    if (target) document.getElementById(target)?.scrollIntoView();
  }, []);

  const cv = cvAttachment(profile.data);
  const [education, certificates, studies] = learning.data ?? [null, null, null];

  return (
    <Layout base="" cv={cv}>
      <Hero availability={profile.data?.availability ?? null} cv={cv} />
      <Work entries={work.data ?? {}} />
      <Approach />
      <Experience rows={experienceRows(experience.data)} learning={learningCards(education, certificates, studies)} />
      <Stack groups={stackGroups(skills.data)} />
      <Outside />
      <Contact cv={cv} />
    </Layout>
  );
}
