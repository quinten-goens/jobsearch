"""Complete regional lists, to fill the gaps the hand-built sheet left.

The sheet had 4 of the 19 Brussels communes and a scattering of research
centres rather than Belgium's universities. Where a sector has a *known,
bounded* membership -- the 19 communes, the Flemish/French university systems,
the EU institutions -- the honest move is to enumerate it rather than hope a
search surfaces the rest.

These lists are curated (they change on the timescale of law, not of hiring)
and carry the context Sarah needs: what the body is, roughly how big, what
language it works in, and why it's relevant. Careers URLs are left to
`discover.py`, which is better at finding them than a hardcoded guess.
"""

# --------------------------------------------------------------- communes
# All 19 communes of the Brussels-Capital Region. Population figures are
# approximate (~2024) and are there to convey scale, not to be precise.
# Language: officially bilingual FR/NL region-wide; the working language of
# each administration is noted where it skews.
BRUSSELS_COMMUNES = [
    ("Anderlecht", 126000, "FR/NL", "Large, diverse, strong social services arm."),
    ("Auderghem / Oudergem", 34000, "FR/NL", "Small, residential, near EU quarter."),
    ("Berchem-Sainte-Agathe / Sint-Agatha-Berchem", 25000, "FR/NL", "Small western commune."),
    ("Bruxelles-Ville / Stad Brussel", 188000, "FR/NL",
     "The city proper. Biggest employer of the 19; runs its own international relations desk."),
    ("Etterbeek", 49000, "FR/NL", "Hosts much of the EU quarter and VUB/ULB campuses."),
    ("Evere", 43000, "FR/NL", "Home to NATO HQ."),
    ("Forest / Vorst", 57000, "FR/NL", "Industrial south-west, active social policy."),
    ("Ganshoren", 25000, "FR/NL", "Small north-western commune."),
    ("Ixelles / Elsene", 88000, "FR/NL",
     "ULB main campus, Matonge (Congolese diaspora), strong cultural/social sector."),
    ("Jette", 53000, "FR/NL", "UZ Brussel campus."),
    ("Koekelberg", 22000, "FR/NL", "Smallest by area."),
    ("Molenbeek-Saint-Jean / Sint-Jans-Molenbeek", 98000, "FR/NL",
     "Large migrant population; heavy investment in integration and youth work."),
    ("Saint-Gilles / Sint-Gillis", 50000, "FR/NL",
     "Dense, diverse, large Spanish/Portuguese/Latin American community."),
    ("Saint-Josse-ten-Noode / Sint-Joost-ten-Node", 28000, "FR/NL",
     "Smallest and densest; very high migrant share."),
    ("Schaerbeek / Schaarbeek", 130000, "FR/NL",
     "Second largest; large Turkish and Moroccan communities."),
    ("Uccle / Ukkel", 85000, "FR/NL", "Affluent south; many international schools."),
    ("Watermael-Boitsfort / Watermaal-Bosvoorde", 25000, "FR/NL", "Green, residential."),
    ("Woluwe-Saint-Lambert / Sint-Lambrechts-Woluwe", 59000, "FR/NL",
     "UCLouvain Brussels health campus."),
    ("Woluwe-Saint-Pierre / Sint-Pieters-Woluwe", 41000, "FR/NL",
     "Affluent east; large expat population."),
]

# Communes just outside the Region that Sarah could plausibly commute to.
BRUSSELS_PERIPHERY = [
    ("Zaventem", 34000, "NL", "Airport commune; many international employers."),
    ("Machelen", 14000, "NL", "Airport-adjacent business parks."),
    ("Vilvoorde", 46000, "NL", "Northern periphery, growing diverse population."),
    ("Grimbergen", 38000, "NL", "Northern periphery."),
    ("Asse", 33000, "NL", "North-west periphery."),
    ("Dilbeek", 43000, "NL", "Western periphery, Flemish Brabant."),
    ("Sint-Pieters-Leeuw", 34000, "NL", "South-west periphery."),
    ("Beersel", 26000, "NL", "Southern periphery."),
    ("Sint-Genesius-Rode / Rhode-Saint-Genese", 18000, "NL/FR",
     "Facility commune; officially Flemish with French-language facilities."),
    ("Hoeilaart", 11000, "NL", "South-east, Sonian Forest."),
    ("Overijse", 25000, "NL", "South-east periphery, sizeable expat community."),
    ("Tervuren", 22000, "NL", "Home to the AfricaMuseum; large expat community."),
    ("Kraainem", 14000, "NL/FR", "Facility commune, eastern edge."),
    ("Wezembeek-Oppem", 14000, "NL/FR", "Facility commune, eastern edge."),
    ("Wemmel", 16000, "NL/FR", "Facility commune, northern edge."),
    ("Drogenbos", 5000, "NL/FR", "Facility commune, southern edge."),
    ("Linkebeek", 5000, "NL/FR", "Facility commune, southern edge."),
    ("Waterloo", 30000, "FR", "Walloon Brabant; large international community."),
    ("Braine-l'Alleud", 40000, "FR", "Walloon Brabant, southern commute."),
    ("La Hulpe", 7000, "FR", "Walloon Brabant; several corporate HQs."),
    ("Rixensart", 22000, "FR", "Walloon Brabant."),
    ("Wavre", 34000, "FR", "Walloon Brabant capital."),
    ("Ottignies-Louvain-la-Neuve", 32000, "FR", "UCLouvain's main campus town."),
    ("Leuven", 102000, "NL", "KU Leuven; 25 min by train from Brussels."),
    ("Mechelen", 87000, "NL", "Between Brussels and Antwerp."),
    ("Halle", 41000, "NL", "Southern periphery, direct rail to Brussels."),
]

# ------------------------------------------------------------- universities
# (name, city, language, students, description, has_anthropology)
# Sarah wants an anthropology PhD, so the anthropology flag drives her filter.
BELGIAN_UNIVERSITIES = [
    ("KU Leuven", "Leuven", "NL/EN", 65000,
     "Belgium's largest university. Social & Cultural Anthropology research group; "
     "IMMRC (Interculturalism, Migration and Minorities Research Centre).", True),
    ("Ghent University (UGent)", "Ghent", "NL/EN", 50000,
     "Large research university. Department of Conflict and Development Studies; "
     "CESSMIR migration centre; strong African studies.", True),
    ("Université libre de Bruxelles (ULB)", "Brussels", "FR/EN", 38000,
     "Francophone, Brussels-based. LAMC (Laboratoire d'anthropologie des mondes "
     "contemporains) is the anthropology centre; strong Latin America links.", True),
    ("UCLouvain", "Louvain-la-Neuve", "FR/EN", 40000,
     "Largest francophone university. LAAP (Laboratoire d'anthropologie prospective) "
     "does prospective/development anthropology.", True),
    ("Vrije Universiteit Brussel (VUB)", "Brussels", "NL/EN", 22000,
     "Brussels Dutch-language university. Brussels School of Governance; "
     "Institute for European Studies; social/cultural anthropology within sociology.", True),
    ("University of Antwerp (UAntwerpen)", "Antwerp", "NL/EN", 22000,
     "CeMIS (Centre for Migration and Intercultural Studies); IOB Institute of "
     "Development Policy.", True),
    ("Université de Liège (ULiège)", "Liège", "FR/EN", 26000,
     "Francophone; LASC (Laboratoire d'anthropologie sociale et culturelle).", True),
    ("Université de Mons (UMONS)", "Mons", "FR", 9000,
     "Francophone; social sciences and translation/interpreting.", False),
    ("Université de Namur (UNamur)", "Namur", "FR", 7000,
     "Francophone; development studies and economics.", False),
    ("Hasselt University (UHasselt)", "Hasselt", "NL/EN", 7000,
     "Smaller Flemish university; no anthropology department.", False),
    ("Université Saint-Louis Bruxelles (UCLouvain Saint-Louis)", "Brussels", "FR", 4000,
     "Francophone Brussels; now part of UCLouvain. Political and social sciences.", False),
    ("College of Europe", "Bruges / Natolin", "EN/FR", 500,
     "Elite postgraduate EU-affairs college. Not a PhD route, but a hiring "
     "employer and a network hub.", False),
    ("Royal Military Academy", "Brussels", "FR/NL", 1000,
     "Defence-oriented; security studies.", False),
    ("Antwerp Management School", "Antwerp", "EN", 2000, "Business school.", False),
    ("Vlerick Business School", "Brussels / Ghent / Leuven", "EN", 2000,
     "Business school with a Brussels campus.", False),
    ("Institute of Tropical Medicine (ITM)", "Antwerp", "EN/NL", 800,
     "Global health research and teaching; strong Global South partnerships and "
     "medical-anthropology adjacent work.", True),
    ("United Nations University - CRIS", "Bruges", "EN", 100,
     "UN University's comparative regional integration studies institute.", False),
    ("IHECS", "Brussels", "FR", 2000,
     "Francophone communication school; applied comms and journalism.", False),
    ("Université ouverte / Open Universiteit", "Multiple", "FR/NL", 0,
     "Distance learning.", False),
]

# Flemish/Walloon university colleges (hogescholen / hautes écoles) worth
# knowing as employers, though not PhD-granting.
BELGIAN_COLLEGES = [
    ("Erasmushogeschool Brussel", "Brussels", "NL", 6000, "Brussels Dutch-language college."),
    ("Odisee", "Brussels / Ghent", "NL", 12000, "Applied sciences, social work."),
    ("HE2B (Haute École Bruxelles-Brabant)", "Brussels", "FR", 8000, "Francophone college."),
    ("Haute École Léonard de Vinci", "Brussels", "FR", 8000, "Francophone college."),
    ("EPHEC", "Brussels", "FR", 5000, "Francophone applied economics college."),
    ("LUCA School of Arts", "Brussels / Ghent", "NL", 4000, "Arts school."),
]
