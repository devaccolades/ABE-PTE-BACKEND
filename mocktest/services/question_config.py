VALID_SKILLS = {"speaking", "writing", "reading", "listening"}
CANONICAL_TRAIT_SKILL_CONTRACTS = {
    ("read_aloud", "content"): {"speaking"},
    ("read_aloud", "oral_fluency"): {"speaking"},
    ("read_aloud", "pronunciation"): {"speaking"},
}
SUBQUESTION_SUBSECTIONS = {"fib_dropdown", "l_fill_in_blanks"}
CANONICAL_TASK_SKILLS = {
    "read_aloud": {"speaking"},
}


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


def effective_question_skill_maxima(question):
    maxima = {
        skill: getattr(question, f"{skill}_score_max") or 0
        for skill in VALID_SKILLS
    }
    allowed = CANONICAL_TASK_SKILLS.get(question.subsection.name)
    if allowed is not None:
        for skill in VALID_SKILLS - allowed:
            maxima[skill] = 0
    return maxima
