from collections.abc import Sequence

from claimledger.domain import ConfirmedProduct, ProductCandidate
from claimledger.errors import IdentityRequiredError


def confirm_candidate(
    candidates: Sequence[ProductCandidate], selected_report_no: str
) -> ConfirmedProduct:
    if not selected_report_no.strip():
        raise IdentityRequiredError("product selection is required")

    report_numbers = [candidate.report_no for candidate in candidates]
    if len(report_numbers) != len(set(report_numbers)):
        raise IdentityRequiredError("duplicate report numbers prevent product confirmation")

    for candidate in candidates:
        if candidate.report_no == selected_report_no:
            return ConfirmedProduct(product=candidate, confirmed_by_user=True)
    raise IdentityRequiredError("selected report number is not present in candidates")


def require_confirmed_product(product: ConfirmedProduct | None) -> ConfirmedProduct:
    if product is None:
        raise IdentityRequiredError("user-confirmed product is required")
    return product
