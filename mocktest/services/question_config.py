VALID_SKILLS = {"speaking", "writing", "reading", "listening"}
CANONICAL_TRAIT_SKILL_CONTRACTS = {
    ("read_aloud", "content"): {"speaking", "reading"},
}
SUBQUESTION_SUBSECTIONS = {"fib_dropdown", "l_fill_in_blanks"}


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
