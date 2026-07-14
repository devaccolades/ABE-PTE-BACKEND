from examinor.scoring.validators import rubric_maxima


VALID_SKILLS = {"speaking", "writing", "reading", "listening"}
CANONICAL_TRAIT_SKILL_CONTRACTS = {
    ("read_aloud", "content"): {"speaking", "reading"},
}
SUBQUESTION_SUBSECTIONS = {"fib_dropdown", "l_fill_in_blanks"}


def normalized_trait_skills(subsection, trait):
    required = CANONICAL_TRAIT_SKILL_CONTRACTS.get((subsection.name, trait))
    if required is not None:
        return set(required)

    configured = (subsection.trait_skill_map or {}).get(trait, [])
    if isinstance(configured, str):
        configured = [configured]
    return set(configured) & VALID_SKILLS


def expected_question_skill_maxima(subsection):
    expected = {skill: 0.0 for skill in VALID_SKILLS}
    for trait, maximum in rubric_maxima(subsection.rubric).items():
        for skill in normalized_trait_skills(subsection, trait):
            expected[skill] += maximum
    return {skill: maximum for skill, maximum in expected.items() if maximum > 0}


def canonical_trait_skill_map(subsection):
    trait_map = dict(subsection.trait_skill_map or {})
    changed = False
    for (subsection_name, trait), skills in CANONICAL_TRAIT_SKILL_CONTRACTS.items():
        if subsection.name != subsection_name:
            continue
        canonical = sorted(skills)
        configured = trait_map.get(trait, [])
        if isinstance(configured, str):
            configured = [configured]
        if set(configured) != skills:
            trait_map[trait] = canonical
            changed = True
    return trait_map, changed
