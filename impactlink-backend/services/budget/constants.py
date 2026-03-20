from typing import Set
from .models import CategoryType

# Compliance bucket membership — single source of truth
PERSONNEL_CATEGORIES: Set[CategoryType] = {
    CategoryType.FIELD_STAFF,
    CategoryType.ADMIN_STAFF,
    CategoryType.PROJECT_LEAD,
    CategoryType.CONSULTANTS,
}

INDIRECT_CATEGORIES_DEFAULT: Set[CategoryType] = {
    CategoryType.INDIRECT_OVERHEAD,
    CategoryType.FACILITIES,
    CategoryType.IT_COMMUNICATIONS,
}

DIRECT_SERVICE_CATEGORIES: Set[CategoryType] = {
    CategoryType.PROGRAM_ACTIVITIES,
    CategoryType.TRAINING_EDUCATION,
    CategoryType.OUTREACH,
}
