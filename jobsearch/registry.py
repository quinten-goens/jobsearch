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

# ---------------------------------------------------------------- hospitals
# (name, city, language, staff, description)
# Big hospitals are large multilingual employers with real non-clinical
# functions: patient mediation, social work, international patient services,
# communications, HR, research administration.
BELGIAN_HOSPITALS = [
    ("UZ Brussel", "Brussels (Jette)", "NL/FR/EN", 3900,
     "VUB's university hospital. Intercultural mediation and social services."),
    ("Cliniques universitaires Saint-Luc (UCLouvain)", "Brussels (Woluwe)", "FR/EN", 5800,
     "UCLouvain's university hospital; large international patient service."),
    ("Hôpital Erasme (ULB)", "Brussels (Anderlecht)", "FR/EN", 3300,
     "ULB's university hospital, part of the H.U.B network."),
    ("H.U.B (Hôpital Universitaire de Bruxelles)", "Brussels", "FR/NL/EN", 6000,
     "Umbrella grouping Erasme, Bordet and HUDERF."),
    ("Institut Jules Bordet", "Brussels (Anderlecht)", "FR/EN", 1200,
     "Cancer institute; strong research arm."),
    ("HUDERF (Queen Fabiola Children's Hospital)", "Brussels (Laeken)", "FR/NL", 1000,
     "Paediatric university hospital."),
    ("CHU Brugmann", "Brussels (Laeken)", "FR/NL", 3300,
     "Large public hospital; very diverse patient population, mediation roles."),
    ("CHU Saint-Pierre", "Brussels (city centre)", "FR/NL/EN", 2900,
     "Public hospital with a major migrant and refugee health programme; "
     "infectious diseases reference centre."),
    ("Chirec (Delta, Braine, Ste-Anne)", "Brussels", "FR/EN", 3000,
     "Private hospital network across Brussels."),
    ("Cliniques de l'Europe / Europa Ziekenhuizen", "Brussels (Uccle/Etterbeek)",
     "FR/NL/EN", 2000, "Bilingual network with a large expat patient base."),
    ("Epicura", "Hainaut", "FR", 2600, "Public hospital network in Hainaut."),
    ("UZ Leuven", "Leuven", "NL/EN", 9000,
     "Belgium's largest hospital; KU Leuven's teaching hospital."),
    ("UZ Gent", "Ghent", "NL/EN", 6500, "UGent's university hospital."),
    ("UZA (Antwerp University Hospital)", "Antwerp", "NL/EN", 3000,
     "University of Antwerp's teaching hospital."),
    ("CHU de Liège", "Liège", "FR", 5500, "ULiège's university hospital."),
    ("CHU UCL Namur", "Namur / Yvoir", "FR", 3000, "UCLouvain's Namur network."),
    ("Institute of Tropical Medicine clinic", "Antwerp", "NL/EN/FR", 500,
     "Travel and tropical medicine clinic attached to ITM."),
]

# ------------------------------------- international orgs with remote hiring
# (name, hq, language, staff, description, remote)
# Sarah asked specifically about worldwide-remote roles: these organisations
# either hire globally-remote or run rosters/consultant pools that don't
# require being in a given city.
INTERNATIONAL_REMOTE = [
    ("United Nations Volunteers (UNV)", "Bonn / global", "EN/FR/ES", 1000,
     "Online Volunteering plus international UNV assignments; explicit remote "
     "programme.", True),
    ("UNDP", "New York / global", "EN/FR/ES", 17000,
     "Large consultant and roster system; many home-based contracts.", True),
    ("UNICEF", "New York / global", "EN/FR/ES", 18000,
     "Consultancy roster with home-based terms of reference.", True),
    ("UNHCR", "Geneva / global", "EN/FR/ES", 20000,
     "Refugee agency; affiliate and consultant schemes, plus a Brussels office.",
     True),
    ("WHO", "Geneva / global", "EN/FR/ES", 8000,
     "Consultant roster; some home-based contracts.", True),
    ("IOM (International Organization for Migration)", "Geneva / global",
     "EN/FR/ES", 20000,
     "Migration agency; large consultant pool and a Brussels regional office.",
     True),
    ("UN Women", "New York / global", "EN/FR/ES", 3000,
     "Gender equality agency; home-based consultancies.", True),
    ("OHCHR", "Geneva / global", "EN/FR/ES", 1500,
     "UN Human Rights; consultant and fellowship routes.", True),
    ("ILO", "Geneva / global", "EN/FR/ES", 3500,
     "Labour standards; external collaboration contracts.", True),
    ("FAO", "Rome / global", "EN/FR/ES", 11000,
     "Food and agriculture; large home-based consultant roster.", True),
    ("WFP", "Rome / global", "EN/FR/ES", 22000,
     "Food assistance; consultant roster and a Brussels liaison office.", True),
    ("UNESCO", "Paris / global", "EN/FR/ES", 2000,
     "Education and culture; consultancies.", True),
    ("UNRWA", "Amman / global", "EN/FR", 30000, "Palestine refugee agency.", False),
    ("UNODC", "Vienna / global", "EN/FR/ES", 2000,
     "Drugs and crime; consultant roster.", True),
    ("UNFPA", "New York / global", "EN/FR/ES", 4000,
     "Population fund; home-based consultancies.", True),
    ("OECD", "Paris", "EN/FR", 3300,
     "Policy research; consultant contracts, some remote.", True),
    ("Council of Europe", "Strasbourg", "EN/FR", 2200,
     "Human rights body; consultant and expert rosters.", True),
    ("OSCE", "Vienna / field", "EN/FR", 3500,
     "Security organisation; secondment and consultant routes.", False),
    ("Amnesty International (International Secretariat)", "London / global",
     "EN/FR/ES", 800, "Distributed secretariat; hires remotely in several hubs.",
     True),
    ("Human Rights Watch", "New York / global", "EN/FR/ES", 550,
     "Hires researchers based in many countries.", True),
    ("Oxfam International", "Nairobi / global", "EN/FR/ES", 10000,
     "Confederation secretariat; several roles are location-flexible.", True),
    ("Save the Children International", "London / global", "EN/FR/ES", 25000,
     "Large international NGO with home-based and roster roles.", True),
    ("Médecins Sans Frontières (Operational Centre Brussels)", "Brussels",
     "FR/EN/ES", 3000,
     "MSF's Brussels operational centre; HQ and field roles.", False),
    ("Norwegian Refugee Council", "Oslo / global", "EN/FR/ES", 15000,
     "NORCAP roster deploys experts globally.", True),
    ("Danish Refugee Council", "Copenhagen / global", "EN/FR", 9000,
     "Standby roster and country offices.", True),
    ("International Crisis Group", "Brussels / global", "EN/FR/ES", 150,
     "Conflict analysis; analysts based in the regions they cover. Brussels HQ.",
     True),
    ("Internews", "Washington / global", "EN/FR/ES", 1000,
     "Media development; many remote roles.", True),
    ("Open Society Foundations", "New York / global", "EN/FR/ES", 800,
     "Grantmaker; hires across hubs including Brussels.", False),
    ("Global Fund", "Geneva", "EN/FR", 900, "Health financing; consultant roster.",
     True),
    ("GAVI", "Geneva", "EN/FR", 500, "Vaccine alliance; some remote roles.", True),
]

# ------------------------------------------- niche government & public bodies
# (name, level, language, description)
# Smaller public bodies that hire policy, comms and research profiles but
# rarely appear on the big boards.
BELGIAN_PUBLIC_BODIES = [
    ("Myria (Federal Migration Centre)", "Federal", "FR/NL/EN",
     "Independent federal migration rights body. Research, policy, advocacy."),
    ("Unia (Interfederal Equal Opportunities Centre)", "Interfederal", "FR/NL/EN",
     "Anti-discrimination body; casework, research, policy."),
    ("Institute for the Equality of Women and Men", "Federal", "FR/NL",
     "Federal gender equality body."),
    ("Federal Institute for Sustainable Development", "Federal", "FR/NL",
     "SDG coordination across federal government."),
    ("Comité P / Comité R", "Federal", "FR/NL",
     "Police and intelligence oversight committees."),
    ("Federal Ombudsman", "Federal", "FR/NL", "Handles complaints against federal bodies."),
    ("Conseil supérieur de la Justice", "Federal", "FR/NL", "Judicial oversight."),
    ("Belgian Development Agency (Enabel)", "Federal", "FR/NL/EN",
     "Belgium's development agency; country programmes and Brussels HQ."),
    ("BIO (Belgian Investment Company for Developing Countries)", "Federal",
     "FR/NL/EN", "Development finance institution."),
    ("Finexpo", "Federal", "FR/NL", "Export credit support."),
    ("Sciensano", "Federal", "FR/NL/EN", "Public health research institute."),
    ("FPS Justice - International cooperation", "Federal", "FR/NL",
     "Judicial cooperation and international files."),
    ("FPS Social Security - International relations", "Federal", "FR/NL",
     "Bilateral social security agreements."),
    ("Fedasil", "Federal", "FR/NL/EN",
     "Reception agency for asylum seekers. Large recruiter; social and policy roles."),
    ("CGRA / CGVS", "Federal", "FR/NL/EN",
     "Office of the Commissioner General for Refugees; protection officers, "
     "country-of-origin researchers."),
    ("Conseil du contentieux des étrangers", "Federal", "FR/NL",
     "Immigration appeals court."),
    ("Office des Étrangers / Dienst Vreemdelingenzaken", "Federal", "FR/NL",
     "Immigration office."),
    ("Brussels International", "Regional (Brussels)", "FR/NL/EN",
     "The Brussels Region's international relations department."),
    ("hub.brussels", "Regional (Brussels)", "FR/NL/EN",
     "Brussels business support agency; international trade attachés."),
    ("Innoviris", "Regional (Brussels)", "FR/NL/EN",
     "Brussels research funding agency."),
    ("perspective.brussels", "Regional (Brussels)", "FR/NL",
     "Brussels planning and statistics bureau."),
    ("Bruxelles Prévention & Sécurité", "Regional (Brussels)", "FR/NL",
     "Regional prevention and security body."),
    ("equal.brussels", "Regional (Brussels)", "FR/NL",
     "Brussels equal opportunities administration."),
    ("Brussels Housing (Bruxelles Logement)", "Regional (Brussels)", "FR/NL",
     "Regional housing administration."),
    ("Iriscare", "Regional (Brussels)", "FR/NL",
     "Brussels health and welfare administration."),
    ("Bruxelles Environnement / Leefmilieu Brussel", "Regional (Brussels)",
     "FR/NL/EN", "Regional environment administration."),
    ("Brussels Studies Institute", "Regional (Brussels)", "FR/NL/EN",
     "Urban research; links the Brussels universities."),
    ("Wallonie-Bruxelles International (WBI)", "Community (FR)", "FR/EN/ES",
     "Francophone Belgium's international relations agency. Strong Latin "
     "America programme — a direct fit for Spanish."),
    ("Flanders Department of Foreign Affairs", "Community (NL)", "NL/EN",
     "Flemish government's international relations department."),
    ("APEFE", "Community (FR)", "FR/ES",
     "Francophone technical cooperation agency; Latin America programmes."),
    ("Délégation générale Wallonie-Bruxelles", "Community (FR)", "FR/ES",
     "Francophone Belgium's overseas delegations."),
    ("CPAS de Bruxelles / OCMW Brussel", "Local (Brussels)", "FR/NL",
     "Public social welfare centre; every commune has one. Large social-work "
     "and integration employer."),
    ("Actiris International", "Regional (Brussels)", "FR/NL/EN",
     "Actiris's international recruitment and EURES arm."),
    ("Bruxelles Formation", "Regional (Brussels)", "FR",
     "Francophone vocational training body."),
    ("VDAB Brussel", "Regional (Brussels)", "NL",
     "Flemish employment service, Brussels branch."),
]
