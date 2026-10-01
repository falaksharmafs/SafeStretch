"""Rule-based intervention ideas. These are prioritisation hints, not engineering advice."""


def suggest(row) -> list[str]:
    g = lambda k: (row.get(k) or 0) if hasattr(row, "get") else (getattr(row, k, 0) or 0)
    tips = []
    if g("junctions_nearby") >= 3:
        tips.append("Junction cluster: review signage, sight lines, and speed-calming at approaches.")
    if g("alcohol_nearby") >= 1:
        tips.append("Alcohol outlets nearby: consider targeted night-time enforcement / breath-test checkpoints.")
    if g("curvature") >= 1.15:
        tips.append("Sharp curvature: add chevron markers, advisory speed signs, and reflective edge lines.")
    if g("schools_nearby") >= 1:
        tips.append("School zone: enforce reduced speed limit and add marked crossings / guard rails.")
    if g("crossings_nearby") >= 2 and g("speed_limit") >= 50:
        tips.append("Pedestrian crossings on a fast road: consider raised crossings or signal-controlled crossings.")
    if g("speed_limit") >= 60:
        tips.append("High speed limit: consider speed cameras or variable speed limits.")
    return tips or ["No single dominant factor - schedule a site audit to look for local causes."]
