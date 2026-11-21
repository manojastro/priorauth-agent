"""Roles for the login stub. Production would map these from the organisation's SSO groups."""

PA_COORDINATOR = "pa_coordinator"
PA_REVIEWER = "pa_reviewer"
ROLES = (PA_COORDINATOR, PA_REVIEWER)

# Demo users (synthetic). No passwords: this is a stub, documented as such.
DEMO_USERS = {
    "coord.demo": PA_COORDINATOR,
    "reviewer.demo": PA_REVIEWER,
    "reviewer2.demo": PA_REVIEWER,
}
