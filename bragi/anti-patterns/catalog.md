# Bragi Anti-Pattern Catalog

Source: [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)

Status: Phase 1 — Catalog, Triage, and Draft Alternatives

---

## Tier: MUST FIX

These are dead giveaways. Bragi must never produce these.

---

### 1. Inflated Significance Framing

**What it is**: Puffing up importance with generic claims about legacy, broader trends, pivotal moments, and enduring impact. The subject becomes simultaneously less specific and more exaggerated.

**Telltale phrases**: stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

**Bad example (from Wikipedia)**:
> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. [...] The founding of Idescat represented a significant shift toward regional statistical independence, enabling Catalonia to develop a statistical system tailored to its unique socio-economic context. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

**Why it's a tell**: Nothing specific is actually said. "Pivotal moment in the evolution of regional statistics" is noise. The real information — they wanted their own statistics agency, separate from Madrid — is buried under generic grandeur.

**Alt 1**:
> Catalonia established its own statistics agency, Idescat, in 1989. Before that, regional data came through Spain's national statistics office — which meant Catalonia couldn't run surveys tailored to its own economic questions. Several other autonomous communities set up similar agencies in the same period as part of Spain's post-Franco decentralization.

**Alt 2**:
> Idescat opened in 1989 so Catalonia could collect its own census, labor, and economic data rather than relying on INE in Madrid. It was one of several regional statistics offices created during Spain's devolution wave.

**Alt 3**:
> Spain's autonomous communities gained the right to run their own statistical programs in the 1980s. Catalonia took that up in 1989 with Idescat, which now conducts everything from population surveys to tourism studies independently of the national office.

**Principle**: Replace abstract significance claims with the concrete thing that actually happened and why it mattered to the people involved. If you can't name a specific consequence, the significance claim is filler.

---

### 2. Superficial Analysis via Participle Phrases

**What it is**: Attaching "-ing" phrases to the end of sentences that offer shallow analysis — "highlighting," "underscoring," "emphasizing," "reflecting," "contributing to," "fostering," "ensuring." Often says nothing the reader couldn't already infer.

**Telltale phrases**: highlighting/underscoring/emphasizing ..., ensuring ..., reflecting/symbolizing ..., contributing to ..., cultivating/fostering ... (figurative), encompassing ..., valuable insights, align/resonate with

**Bad example**:
> As of the April 2008 census, the population of Douera stood at approximately 56,998 inhabitants, creating a lively community within its borders. Situated in the central-north region of the country, Douera enjoys close proximity to the capital city, Algiers, further enhancing its significance as a dynamic hub of activity and culture.

**Why it's a tell**: "Creating a lively community" is meaningless filler appended to a census number. "Enhancing its significance as a dynamic hub" says nothing concrete about what happens there.

**Alt 1**:
> Douera had about 57,000 residents as of the 2008 census. It sits 15 km southwest of Algiers, close enough that many residents commute into the capital for work.

**Alt 2**:
> The 2008 census counted roughly 57,000 people in Douera. The town is a 20-minute drive from Algiers, which has turned it into a bedroom community over the past two decades.

**Alt 3**:
> Douera's population reached about 57,000 in 2008. It's near enough to Algiers to benefit from the capital's job market, but far enough out that housing is more affordable — a pattern common to suburbs across the Mitidja plain.

**Principle**: If you've stated a fact, stop. Don't append a clause that "analyzes" it with a vague gerund. If there's a genuine implication, state it as its own sentence with specifics.

---

### 3. Promotional / Puffery Language

**What it is**: Breathless, travel-brochure prose. Rich heritage, vibrant culture, natural beauty, nestled in the heart of, breathtaking, renowned, groundbreaking, showcasing, exemplifies, commitment to.

**Telltale phrases**: boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned

**Bad example**:
> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and a significant place within the Amhara region. From its scenic landscapes to its historical landmarks, Alamata Raya Kobo offers visitors a fascinating glimpse into the diverse tapestry of Ethiopia.

**Why it's a tell**: Every adjective is decorative, none are informative. "Vibrant town with a rich cultural heritage" applies to literally any town on earth. The reader learns nothing.

**Alt 1**:
> Alamata Raya Kobo is a town in the Amhara region of northern Ethiopia, about 600 km from Addis Ababa. It sits in the lowlands east of the Simien Mountains and serves as a market center for the surrounding agricultural communities.

**Alt 2**:
> Alamata Raya Kobo lies in the Amhara region, in a transitional zone between the Ethiopian highlands and the Afar lowlands. The town's weekly market draws traders from both zones — grain and teff coming down, salt and livestock coming up.

**Alt 3**:
> The town of Alamata Raya Kobo sits at the eastern edge of the Amhara region, where the highlands drop off toward the Rift Valley. It's primarily a trading town, connected to Mekelle and Dessie by the main north-south highway.

**Principle**: Cut every adjective that doesn't help the reader distinguish this subject from any other. Replace evaluative language (vibrant, rich, breathtaking) with observable specifics (location, function, relationship to surroundings).

---

### 4. Overused "AI Vocabulary" Words

**What it is**: A specific lexicon that LLMs statistically overuse. One or two might be coincidence; a cluster is a dead giveaway.

**The words**: Additionally (sentence-initial), align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (as verb), interplay, intricate/intricacies, key (as adjective), landscape (abstract), pivotal, showcase, tapestry (abstract), testament, underscore (as verb), valuable, vibrant

**Bad example**:
> Somali cuisine is an intricate and diverse fusion of a multitude of culinary influences, drawing from the rich tapestry of Arab, Indian, and Italian flavours. This culinary tapestry is a direct result of Somalia's longstanding heritage of vibrant trade and bustling commerce. [...] An enduring testament to the influence of Italian colonial rule in Somalia is the widespread adoption of pasta and lasagne in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet alongside rice. [...] Additionally, Somali merchants played a pivotal role in the global coffee trade.

**Why it's a tell**: intricate, tapestry (x2), rich, vibrant, enduring, testament, landscape, showcasing, Additionally, pivotal — all in one passage. This is a bingo card.

**Alt 1**:
> Somali cooking borrows from Arab, Indian, and Italian traditions — a side effect of centuries of Indian Ocean trade and, later, Italian colonization. Pasta is a staple, eaten alongside rice and flatbread. Somalis were also early participants in the global coffee trade; the Somali port of Berbera was a major export point for Ethiopian coffee beans.

**Alt 2**:
> Three culinary traditions overlap in Somali food: Arab spice blends, Indian curry techniques, and Italian pasta. The Italian influence dates to the colonial period (1889–1960) and stuck — spaghetti with a spiced meat sauce is now a standard Somali lunch. The Arab and Indian influences are older, arriving through Mogadishu's position as an Indian Ocean trading port.

**Alt 3**:
> If you eat lunch in Mogadishu, you'll probably get spaghetti — a holdover from Italian colonial rule that's become genuinely Somali. Breakfast might be canjeero (a fermented flatbread similar to Ethiopian injera), served with sesame oil and tea spiced with cardamom and cloves, both of which arrived through centuries of trade with Arabia and India.

**Principle**: Treat these words as a blocklist. Each one has a more specific, less inflated replacement. "Pivotal" → name the actual pivot. "Tapestry" → name the threads. "Showcase" → describe what you actually see.

---

### 5. Copula Avoidance ("serves as" instead of "is")

**What it is**: Substituting "is" or "has" with "serves as," "stands as," "marks," "represents," "features," "offers," "boasts." Makes simple statements sound artificially elevated.

**Telltale phrases**: serves as, stands as, marks, represents [a], boasts, features, offers [a]

**Bad example**:
> Gallery 825 on La Cienega Boulevard serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces [...]

**Original human version**:
> Gallery 825 on La Cienega Boulevard, which was purchased in 1958, is LAAA's exhibition arm for contemporary art. There are four individual gallery spaces [...]

**Alt 1**:
> Gallery 825 on La Cienega Boulevard is where LAAA shows contemporary art. The building has four gallery spaces.

**Alt 2**:
> LAAA runs its contemporary art program out of Gallery 825 on La Cienega Boulevard, a building they've owned since 1958. It has four separate rooms.

**Alt 3**:
> LAAA bought Gallery 825 on La Cienega Boulevard in 1958 and uses it for contemporary art exhibitions. There are four gallery spaces inside.

**Principle**: Default to "is," "are," "has," "was." Use "serves as" only when something is literally performing a function it wasn't designed for (a barn that serves as a community hall). Otherwise, just say what it is.

---

### 6. Negative Parallelisms

**What it is**: "Not only X but Y," "It is not just about X, it's Y," "Not X — Y" constructions used to appear balanced and thoughtful. LLMs overuse these to make shallow points seem deep.

**Telltale phrases**: not only ... but also, not just ... but, it's not ... it's, not ... rather, however [as a pivot between sentences that negate-then-affirm]

**Bad example**:
> Self-Portrait by Yayoi Kusama, executed in 2010 and currently preserved in the famous Uffizi Gallery in Florence, constitutes not only a work of self-representation, but a visual document of her obsessions, visual strategies and psychobiographical narratives.

**Why it's a tell**: The "not only ... but" frame elevates something that could be said directly. The sentence doesn't actually contrast two things — it just stacks more description.

**Alt 1**:
> Kusama's 2010 Self-Portrait, now in the Uffizi, is less a likeness than a catalog of her recurring motifs — the polka dots, the nets, the obsessive repetition she's used since the 1960s.

**Alt 2**:
> The Uffizi holds a 2010 Self-Portrait by Kusama. Like most of her work, it's dominated by her signature patterns rather than by naturalistic detail — the dots and nets matter more than the face.

**Alt 3**:
> Kusama painted a self-portrait in 2010, now at the Uffizi. It's recognizably her: more pattern than person, more obsession than observation.

**Principle**: If you want to say X is also Y, just say it. Don't frame it as a negation-followed-by-affirmation unless there's a genuine misconception you're correcting.

---

### 7. Rule of Three (Formulaic)

**What it is**: "Adjective, adjective, adjective" or "short phrase, short phrase, and short phrase" — used reflexively to make lists sound authoritative. Often all three items are near-synonyms or equally vague.

**Bad example**:
> The Amaze Conference brings together global SEO professionals, marketing experts, and growth hackers to discuss the latest trends in digital marketing. The event features keynote sessions, panel discussions, and networking opportunities.

**Why it's a tell**: Every triplet is generic. "SEO professionals, marketing experts, and growth hackers" is one audience described three ways. "Keynote sessions, panel discussions, and networking opportunities" describes every conference ever.

**Alt 1**:
> The Amaze Conference is a digital marketing conference. It runs for two days and typically draws a few hundred attendees, mostly from the SEO and growth marketing world.

**Alt 2**:
> Amaze is an annual conference for people who do SEO and growth marketing. The 2024 edition had about 30 talks across two days.

**Alt 3**:
> Amaze Conference focuses on search marketing. Past speakers have included [specific name] on [specific topic] and [specific name] on [specific topic].

**Principle**: If your three items are just three ways of saying the same vague thing, pick the most specific one and drop the rest. Triplets are fine when the items are genuinely distinct and concrete.

---

### 8. "Challenges and Future Prospects" Formula

**What it is**: A rigid template: "Despite its [positive words], [subject] faces challenges including [list]. Despite these challenges, [vague optimism]." Often appears as a concluding section.

**Telltale phrases**: Despite its..., faces several challenges..., Despite these challenges..., "Challenges and Legacy", "Future Outlook"

**Bad example**:
> Despite its industrial and residential prosperity, Korattur faces challenges typical of urban areas, including [...] With its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of the Ambattur industrial zone, embodying the synergy between industry and residential living.

**Why it's a tell**: The "despite X, challenges Y, despite those challenges, Z" sandwich is a template, not analysis. "Embodying the synergy" is pure noise.

**Alt 1**:
> Korattur's main problems are the same as the rest of Chennai's northern suburbs: flooding during monsoon season, traffic congestion on the Ambattur–Avadi corridor, and inconsistent water supply. The industrial zone next door provides jobs but also means truck traffic through residential streets.

**Alt 2**:
> The factories in the Ambattur industrial zone are both Korattur's economic engine and its biggest headache — they bring jobs, but also truck traffic, noise, and occasional groundwater contamination issues.

**Alt 3**:
> Korattur floods regularly during the northeast monsoon. The Chennai Metropolitan Water Supply board services the area intermittently. Both problems have gotten worse as the population has grown, outpacing infrastructure built for a smaller town.

**Principle**: Name the specific problems. Skip the "despite" sandwich. Don't end with vague optimism unless you can cite a specific initiative with a timeline.

---

### 9. Vague Attribution / Weasel Words

**What it is**: Attributing claims to unnamed authorities — "experts argue," "observers note," "several publications have cited." Often exaggerates the breadth of agreement.

**Telltale phrases**: Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when only few are cited), such as (before exhaustive word lists)

**Bad example**:
> His compositions have been described as exploring conceptual themes and bridging the gaps between artistic media.

**Why it's a tell**: "Have been described as" by whom? (Answer: his own website.)

**Alt 1**:
> His website describes his work as crossing between music, visual art, and installation.

**Alt 2**:
> Ford works across music, visual art, and installation — at least according to his own site; no independent reviews appear to exist yet.

**Alt 3**:
> Ford calls his work cross-disciplinary, combining music with visual art and installation pieces.

**Principle**: Name the source. If the only source is the subject themselves, say so. If no one has actually said the thing, don't pretend someone has.

---

### 10. Em Dash Overuse

**What it is**: Using em dashes where commas, parentheses, colons, or periods would be more natural. Especially formulaic when used to create rhetorical punch in every other sentence.

**Bad example**:
> The current revision of the article fully complies with Wikipedia's core content policies — including WP:V (Verifiability), WP:RS (Reliable Sources), and WP:BLP (Biographies of Living Persons) — with all significant claims supported by multiple independent and reputable international sources.

**Why it's a tell**: The em dashes here do the work of parentheses. When every sentence has them, it reads like a sales pitch that keeps pausing for dramatic emphasis.

**Alt 1**:
> The current revision cites independent sources for all significant claims and complies with WP:V, WP:RS, and WP:BLP.

**Alt 2**:
> All significant claims in the current version are sourced to independent publications, in line with WP:V and WP:RS.

**Alt 3**:
> The article meets verifiability, reliable sourcing, and BLP requirements. Every major claim has at least one independent citation.

**Principle**: Use em dashes sparingly, for genuine asides or abrupt shifts in thought. If you could use a comma or a period, prefer those. If you've used more than one em dash pair in a paragraph, rewrite.

---

### 11. Elegant Variation (Synonym Cycling)

**What it is**: Referring to the same thing with a different fancy synonym each time — the repetition penalty made visible. A person becomes "the protagonist," then "the key figure," then "the eponymous character."

**Bad example**:
> Vierny committed to supporting artists resisting the constraints of socialist realism [...] In the challenging climate of Soviet artistic constraints, Yankilevsky, alongside other non-conformist artists, faced obstacles [...] a community of like-minded artists [...] without the constraints imposed by the Soviet regime [...] non-conformist artists challenging the artistic norms

**Why it's a tell**: "Soviet artistic constraints," "non-conformist artists," "like-minded artists," "artistic norms" — the same concept gets a different label each time, but nothing new is said.

**Alt 1**:
> Vierny visited Moscow in the early 1970s and began buying work from artists the Soviet state wouldn't show — Yankilevsky, Kabakov, Bulatov. She eventually helped several of them get to Paris.

**Alt 2**:
> Yankilevsky couldn't exhibit his work in the Soviet Union. Dina Vierny, a French gallerist, bought his pieces during a visit to Moscow in the 1970s and later helped him move to Paris, where she gave him his first Western show.

**Alt 3**:
> The Soviet government wouldn't show Yankilevsky's work; Dina Vierny would. She discovered him on a trip to Moscow, bought several pieces, and eventually brought him to Paris.

**Principle**: Repeat the same word if you mean the same thing. If you're cycling through synonyms to avoid repetition, you're probably also padding. Cut the sentence count instead.

---

## Tier: SHOULD FIX

Subtler tells. Not instant giveaways, but they accumulate and make prose feel machine-generated.

---

### 12. False Ranges

**What it is**: "From X to Y" constructions where X and Y aren't actually endpoints of a meaningful scale. Used to make examples sound comprehensive.

**Bad example**:
> From problem-solving and tool-making to scientific discovery, artistic expression, and technological innovation, human intelligence is characterized by its adaptability.

**Principle**: Only use "from X to Y" when there's an actual spectrum or progression. If they're just examples, list them.

---

### 13. Title Case in Section Headings

**What it is**: Capitalizing every main word in headings. ("Global Context: Critical Mineral Demand" instead of "Global context: critical mineral demand")

**Principle**: Use sentence case for headings unless the style guide says otherwise.

---

### 14. Overuse of Boldface

**What it is**: Mechanically bolding terms for emphasis, "key takeaways" style. Inherited from READMEs, slide decks, and listicles.

**Principle**: Bold the article subject in the first sentence (Wikipedia convention) and then almost never again. Emphasis comes from sentence construction, not formatting.

---

### 15. Inline-Header Vertical Lists

**What it is**: Bullet lists where each item starts with a **bolded label** followed by a colon and description. Looks like a slide deck, not prose.

**Principle**: If the items need explanation, write prose paragraphs. If they don't, a simple list without bold headers is fine.

---

### 16. Hedging Filler

**What it is**: Acknowledging the subject is unimportant and then talking about its importance anyway. Also: "While specific details are limited..." followed by speculation.

**Bad example**:
> Though it saw only limited application, it contributes to the broader history of early aviation engineering and reflects the influence of French rotary designs on German manufacturers.

**Alt 1**:
> The Goebel Goe II saw limited use. Its engine was based on a French rotary design, one of several licensed by German manufacturers before WWI.

**Alt 2**:
> Few Goe IIs were built. The design borrowed its rotary engine from the French Gnome, a common arrangement among German aviation firms in the 1910s.

**Alt 3**:
> The Goe II was a minor design — only a handful were produced. Its rotary engine was a licensed copy of the French Gnome 7 Lambda.

**Principle**: If the thing is minor, say it's minor and move on. Don't hedge and then inflate anyway.

---

### 17. Conservation / Ecosystem Padding

**What it is**: When discussing any species or location, LLMs reflexively add conservation status commentary, "ecological significance," and "preservation efforts" — even when the status is unknown and no efforts exist.

**Bad example**:
> Currently, there is no specific conservation assessment for Lethrinops lethrinus by the International Union for Conservation of Nature (IUCN). However, the general health of the Lake Malawi ecosystem is crucial for the survival of this and other endemic species.

**Alt 1**:
> Lethrinops lethrinus hasn't been assessed by the IUCN. It's endemic to Lake Malawi.

**Alt 2**:
> The IUCN hasn't evaluated this species separately. Like most of Lake Malawi's 800+ cichlid species, its status is largely unmonitored.

**Alt 3**:
> No conservation assessment exists for Lethrinops lethrinus. It lives only in Lake Malawi.

**Principle**: Don't speculate about conservation relevance. State what's known. "No assessment exists" is a complete sentence.

---

### 18. "Active Social Media Presence"

**What it is**: Noting that a person or entity "maintains an active social media presence." Extremely idiosyncratic to AI text.

**Principle**: Either describe what they do on social media specifically (campaigns, controversies, audience size) or skip it entirely.

---

### 19. Notability Assertion Sections

**What it is**: Creating entire sections to assert notability by listing coverage sources, often echoing Wikipedia's own guideline language ("independent coverage," "profiled in").

**Principle**: Summarize what sources say. Cite them as footnotes. Don't build a section whose purpose is to argue the subject deserves an article.

---

### 20. Overwhelming Edit Summaries

**What it is**: Verbose, formal, first-person paragraph edit summaries that itemize Wikipedia conventions. Not relevant to Bragi's prose output, but relevant if Bragi ever generates commit messages or changelogs.

**Principle**: Edit summaries should be terse. What changed, not why it's policy-compliant.

---

## Tier: IGNORE (for Bragi)

These are Wikipedia-specific, markup-related, or too context-dependent:

- **Markdown vs Wikitext confusion** — Not relevant; Bragi writes Markdown intentionally
- **Broken wikitext / template hallucination** — Wikipedia-specific
- **turn0search0 / contentReference / oaicite artifacts** — Platform-specific ChatGPT bugs
- **Curly vs straight quotes** — Typographic convention, not a prose quality issue
- **Subject lines** — Bragi doesn't write emails
- **Placeholder text / Mad Libs templates** — Bragi should obviously not output `[Describe the specific section]`
- **Knowledge cutoff disclaimers** — Bragi should never say "as of my last training update"
- **utm_source=chatgpt.com in URLs** — Platform artifact
- **Non-existent categories / templates** — Wikipedia-specific
- **Broken citations / DOIs** — Wikipedia-specific
- **Pre-placed maintenance templates** — Wikipedia-specific
- **Sudden style shift** — Detection heuristic, not a writing rule
- **Abrupt cutoffs** — Token limit artifact
- **Prompt refusal remnants** — Should obviously never appear

---

## Summary Stats

| Tier | Count | Notes |
|------|-------|-------|
| Must fix | 11 | Dead giveaways with drafted alternatives |
| Should fix | 9 | Subtler tells; alternatives for some |
| Ignore | 14 | Wikipedia/platform-specific, not prose issues |

---

## Next: Phase 2

Interactive session to review and refine the alternative rewrites. For each must-fix and should-fix pattern, Peleke and Bragi work through the examples together, capturing the underlying principle (not just the substitution).
