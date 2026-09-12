# Phase 8 Dry-Run Test Sites

None of these appear in sites.txt, brands.txt, or the collaborator's
phase1_findings.md — picked specifically to test generalization on truly
unseen sites, spanning different categories and a few deliberately tricky
cases.

## Core set (use these 4 first, as the Phase 8 prompt suggests)

1. **https://www.patagonia.com** — e-commerce, sustainability-focused brand,
   content-heavy site — good contrast to the thinner e-commerce sites already
   studied.
2. **https://www.monday.com** — SaaS, heavy marketing/landing-page structure —
   different flavor of SaaS site than Stripe/Notion/Airtable already covered.
3. **https://www.twilio.com** — B2B/developer-platform, docs-heavy — tests
   whether the checks generalize to a site with a very different content mix
   (marketing pages + technical docs).
4. **https://www.khanacademy.org** — education/nonprofit-adjacent, .org
   domain, different monetization model entirely — good stress test for
   assumptions baked in from commercial sites.

## Extra set (use if you want a wider spread, or to replace any that error out)

5. **https://www.cnet.com** — media/publisher, similar shape to The Verge/
   TechCrunch but a genuinely different site, useful to confirm the
   structured-data and freshness checks aren't overfit to those two.
6. **https://www.doctorswithoutborders.org** — nonprofit, different from
   charity: water (already in the collaborator's set), tests a mission-driven
   org's on-page clarity and corroboration patterns.
7. **A small local business with a very generic, easily-confused name** —
   deliberately search for one yourself rather than using a link here (e.g.
   search "Prime Cleaners [any city]" or "The Coffee House [any city]") — a
   generic name is exactly the entity-clarity-audit stress test (D14/D15),
   and picking it fresh yourself keeps it genuinely unseen even to me.
8. **https://www.wise.com** — fintech, international/multi-entity structure
   (different legal names in different countries) — a natural stress test
   for entity-clarity-audit and freshness-corroboration.

## Why this mix

- Different categories than both research sets (patagonia/monday/twilio/khan
  vs. the SaaS-and-plumbers-heavy original lists).
- At least one docs-heavy site (Twilio) and one non-commercial site (Khan
  Academy) to test assumptions that might be quietly commercial-site-specific.
- Item 7 is intentionally left for you to pick live, since any site I name in
  advance risks not actually being obscure/ambiguous by the time you test it.
