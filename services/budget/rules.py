from typing import Set

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from .models import CategoryType, GrantRules
from .constants import INDIRECT_CATEGORIES_DEFAULT


def resolve_indirect_categories(rules: GrantRules) -> Set[CategoryType]:
    """
    Converts the LLM-extracted indirect_cost_includes strings into a
    set of CategoryType enum values.

    Falls back to INDIRECT_CATEGORIES_DEFAULT for any string that
    doesn't match a valid CategoryType, and logs a warning so the
    mismatch is visible rather than silently dropped.
    """
    if not rules.indirect_cost_includes:
        return INDIRECT_CATEGORIES_DEFAULT.copy()

    resolved: Set[CategoryType] = set()
    valid_values = {e.value: e for e in CategoryType}

    for label in rules.indirect_cost_includes:
        if label in valid_values:
            resolved.add(valid_values[label])
        else:
            # Try a case-insensitive partial match before giving up
            match = next(
                (e for e in CategoryType if label.lower() in e.value.lower()),
                None
            )
            if match:
                resolved.add(match)
                print(f"   ⚠️  Fuzzy-matched indirect category '{label}' → '{match.value}'")
            else:
                print(f"   ⚠️  Could not resolve indirect category '{label}' — skipping.")

    return resolved if resolved else INDIRECT_CATEGORIES_DEFAULT.copy()


def resolve_unallowable_categories(rules: GrantRules) -> Set[CategoryType]:
    """Same resolution logic for unallowable cost categories."""
    valid_values = {e.value: e for e in CategoryType}
    resolved: Set[CategoryType] = set()

    for label in rules.unallowable_costs:
        if label in valid_values:
            resolved.add(valid_values[label])
        else:
            match = next(
                (e for e in CategoryType if label.lower() in e.value.lower()),
                None
            )
            if match:
                resolved.add(match)
                print(f"   ⚠️  Fuzzy-matched unallowable category '{label}' → '{match.value}'")
            else:
                print(f"   ⚠️  Could not resolve unallowable category '{label}' — skipping.")

    return resolved


GRANT_RULES_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a grant compliance analyst.
Extract budget restriction rules from the grant document.
For `indirect_cost_includes` and `unallowable_costs`, use values from this exact list:
{valid_categories}

Do not invent restrictions not present in the document. Use defaults for anything unspecified."""),
    ("user", "Grant Document:\n{grant_document}")
])


def extract_grant_rules(grant_document: str) -> GrantRules:
    print("📋 Extracting grant compliance rules...")
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    chain = GRANT_RULES_PROMPT | llm.with_structured_output(GrantRules)
    try:
        rules = chain.invoke({
            "grant_document": grant_document,
            "valid_categories": [e.value for e in CategoryType],
        })
        print(f"   Personnel cap:     {rules.personnel_cap_pct}%")
        print(f"   Indirect cap:      {rules.indirect_cost_cap_pct}%")
        print(f"   Indirect includes: {rules.indirect_cost_includes}")
        print(f"   Unallowable:       {rules.unallowable_costs}")
        return rules
    except Exception as e:
        print(f"⚠️  Could not extract grant rules, using defaults. Error: {e}")
        return GrantRules()
